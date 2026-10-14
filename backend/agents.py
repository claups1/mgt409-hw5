"""The five Campus Customs agents and how they hand work to each other.

    Boss  <->  Inventory  <->  Accounting  <->  Facilities  <->  Customer Service
    (fully connected: every agent has an ask_<agent> tool for each of the other four)

How a ticket is worked
  1. run_ticket() gives the ticket to the entry agent (Boss by default).
  2. run_agent() drives that agent's PydanticAI loop node by node with agent.iter().
     Each node (prompt in, model request, model response, tool results, final
     output) becomes one record in output/audit_trail.json.
  3. Shop facts come only from the agent's filtered MCP tools (see mcp_link.py).
  4. An ask_<agent> tool runs the other agent's own loop and returns its report.

Guardrails against runaway loops and spend (numbers live in config.py)
  * Loop guard: an agent already in the delegation chain can't be asked again,
    so A -> B -> A ping-pong is impossible.
  * Depth limit: at most MAX_DELEGATION_DEPTH hand-offs deep.
  * Delegation budget: at most MAX_DELEGATIONS_PER_TICKET hand-offs per ticket.
  * Step cap: an agent run stops after MAX_STEPS_PER_AGENT loop steps.
  * Team usage limits: every agent on a ticket shares one usage counter, so the
    request, tool-call, and token limits apply to the whole team.
  * Output caps: MAX_OUTPUT_TOKENS per response, plus length limits in models.py.
Blocked delegation tools are hidden from the model (prepare), and the tool
re-checks the same rules in case it is called anyway.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RunUsage

from audit import AuditTrail, clip, now
from config import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_STEPS_PER_AGENT,
    PROMPTS_DIR,
    TEAM_LIMITS,
    build_model,
    model_settings,
)
from mcp_link import toolset_for
from models import AGENT_TITLES, AuditRecord, SpecialistReport, TicketDecision

AGENT_NAMES = list(AGENT_TITLES)

# One line per agent, shown to the other agents in their ask_<agent> tool description.
AGENT_SCOPES = {
    "boss": "Triages a ticket, decides which specialists to involve, and writes the final plan for a human to approve.",
    "inventory": "Stock on hand by SKU and size, shelf locations, vendors and lead times, and restock proposals.",
    "accounting": "Cash balances, open invoices, payments already made, unit costs and margins, and payment or discount proposals.",
    "facilities": "The shop's lease: rent amount, landlord, due date, and rent payments already recorded.",
    "customer_service": "What a customer can buy at list price and a customer reply draft that passes the privacy check.",
}

OUTPUT_TYPES = {name: SpecialistReport for name in AGENT_NAMES} | {"boss": TicketDecision}


class AgentStopped(Exception):
    """An agent hit a step or usage limit and was stopped."""


@dataclass
class TeamState:
    """Shared by every agent working one ticket."""

    run_id: str
    ticket_id: int
    audit: AuditTrail
    agents: dict[str, Agent]
    usage: RunUsage = field(default_factory=RunUsage)
    delegations: int = 0


@dataclass
class AgentDeps:
    """One per agent run."""

    team: TeamState
    agent: str
    chain: tuple[str, ...]
    step: int = 0

    @property
    def depth(self) -> int:
        return len(self.chain) - 1


# ---------- audit helpers ----------

def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(clip(value), default=str))


def _label(tool_name: str) -> str:
    if tool_name.startswith("ask_") and tool_name[4:] in AGENT_TITLES:
        return f"delegate:{tool_name[4:]}"
    if tool_name == "final_result":
        return "output:final_result"
    return f"mcp:{tool_name}"


def _record(deps: AgentDeps, step_type: str, *, called=None, inputs=None, outputs=None, usage=None) -> None:
    deps.team.audit.append(
        AuditRecord(
            run_id=deps.team.run_id,
            timestamp=now(),
            ticket_id=deps.team.ticket_id,
            agent=deps.agent,
            depth=deps.depth,
            chain=list(deps.chain),
            step=deps.step,
            step_type=step_type,
            called=called or [],
            inputs=_jsonable(inputs),
            outputs=_jsonable(outputs),
            usage=usage,
        )
    )


def _record_node(deps: AgentDeps, node: Any) -> None:
    """Turn one PydanticAI loop node into one audit record."""
    if Agent.is_user_prompt_node(node):
        _record(deps, "task_received", inputs={"prompt": node.user_prompt})

    elif Agent.is_model_request_node(node):
        parts = node.request.parts
        returns = [p for p in parts if isinstance(p, ToolReturnPart)]
        retries = [p for p in parts if isinstance(p, RetryPromptPart)]
        if returns or retries:
            _record(
                deps,
                "tool_results",
                called=[_label(p.tool_name) for p in returns + retries if p.tool_name],
                outputs=[{"tool": p.tool_name, "content": p.content} for p in returns]
                + [{"tool": p.tool_name, "retry": p.model_response()} for p in retries],
            )
        else:
            _record(deps, "model_request", inputs={"parts": [type(p).__name__ for p in parts]})

    elif Agent.is_call_tools_node(node):
        resp = node.model_response
        calls = [p for p in resp.parts if isinstance(p, ToolCallPart)]
        u = resp.usage
        _record(
            deps,
            "model_response",
            called=[_label(c.tool_name) for c in calls],
            inputs=[{"tool": c.tool_name, "args": c.args_as_dict()} for c in calls],
            outputs={"text": "".join(p.content for p in resp.parts if isinstance(p, TextPart))},
            usage={"model": resp.model_name, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
        )

    elif Agent.is_end_node(node):
        out = node.data.output
        _record(deps, "final_output", outputs=out.model_dump() if hasattr(out, "model_dump") else out)


# ---------- delegation ----------

def _blocked_reason(deps: AgentDeps, target: str) -> str | None:
    if target in deps.chain:
        return f"Loop guard: {AGENT_TITLES[target]} is already in the chain ({' -> '.join(deps.chain)})."
    if deps.depth + 1 > MAX_DELEGATION_DEPTH:
        return f"Depth limit: hand-offs may go at most {MAX_DELEGATION_DEPTH} levels deep."
    if deps.team.delegations >= MAX_DELEGATIONS_PER_TICKET:
        return f"Delegation budget used: {MAX_DELEGATIONS_PER_TICKET} hand-offs per ticket."
    return None


def _delegation_tool(target: str) -> Tool[AgentDeps]:
    title = AGENT_TITLES[target]

    async def delegate(ctx: RunContext[AgentDeps], request: str) -> dict:
        d = ctx.deps
        reason = _blocked_reason(d, target)
        if reason:  # only reachable if the model calls a hidden tool anyway
            _record(d, "guardrail", called=[f"delegate:{target}"], inputs={"request": request}, outputs={"blocked": reason})
            return {"status": "blocked", "reason": reason}
        d.team.delegations += 1
        prompt = (
            f"{AGENT_TITLES[d.agent]} asked you about ticket {d.team.ticket_id}:\n\n{request}\n\n"
            "Answer only this request. Use your MCP tools for every fact and cite the tool. "
            "If you need the SKU, size, qty, or a linked lease/invoice id, call get_ticket first; never guess codes."
        )
        try:
            report = await run_agent(target, prompt, d.team, parent_chain=d.chain)
        except AgentStopped as exc:
            return {"status": "stopped", "agent": target, "reason": str(exc)}
        return {"status": "ok", "agent": target, "report": report.model_dump()}

    async def prepare(ctx: RunContext[AgentDeps], tool_def: ToolDefinition) -> ToolDefinition | None:
        return None if _blocked_reason(ctx.deps, target) else tool_def

    return Tool(
        delegate,
        name=f"ask_{target}",
        description=(
            f"Delegate one focused question about the current ticket to the {title} agent. "
            f"{title} handles: {AGENT_SCOPES[target]} "
            "Include the numbers you already have so it doesn't repeat your lookups. "
            "Returns that agent's structured report."
        ),
        prepare=prepare,
    )


def _ticket_context(ctx: RunContext[AgentDeps]) -> str:
    d = ctx.deps
    left = MAX_DELEGATIONS_PER_TICKET - d.team.delegations
    return (
        f"## Run context\n"
        f"- Current ticket: {d.team.ticket_id}\n"
        f"- Delegation chain: {' -> '.join(AGENT_TITLES[a] for a in d.chain)} "
        f"(depth {d.depth} of max {MAX_DELEGATION_DEPTH})\n"
        f"- Hand-offs left for the whole team on this ticket: {left}\n"
        f"- Agents already in the chain can't be asked again; if an ask_ tool is missing, it is blocked "
        f"by a guardrail. Answer with what you have and say what is unresolved."
    )


def build_team(mcp: MCPToolset) -> dict[str, Agent]:
    """Create the five agents, each with its prompt, its MCP tools, and four ask_ tools."""
    model = build_model()
    team: dict[str, Agent] = {}
    for name in AGENT_NAMES:
        agent = Agent(
            model,
            name=name,
            deps_type=AgentDeps,
            output_type=OUTPUT_TYPES[name],
            instructions=(PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"),
            toolsets=[toolset_for(name, mcp)],
            tools=[_delegation_tool(other) for other in AGENT_NAMES if other != name],
            model_settings=model_settings(),
            retries=2,
        )
        agent.instructions(_ticket_context)
        team[name] = agent
    return team


# ---------- the agent loop ----------

async def run_agent(name: str, prompt: str, team: TeamState, parent_chain: tuple[str, ...] = ()) -> Any:
    """Run one agent's loop, auditing every step, and return its structured output."""
    deps = AgentDeps(team=team, agent=name, chain=parent_chain + (name,))
    try:
        async with team.agents[name].iter(
            prompt, deps=deps, usage=team.usage, usage_limits=TEAM_LIMITS
        ) as run:
            async for node in run:
                deps.step += 1
                if deps.step > MAX_STEPS_PER_AGENT:
                    msg = f"Step cap: {AGENT_TITLES[name]} stopped after {MAX_STEPS_PER_AGENT} steps."
                    _record(deps, "guardrail", outputs={"stopped": msg})
                    raise AgentStopped(msg)
                _record_node(deps, node)
        return run.result.output
    except UsageLimitExceeded as exc:
        msg = f"Team usage limit: {exc}"
        _record(deps, "guardrail", outputs={"stopped": msg})
        raise AgentStopped(msg) from exc
    except AgentStopped:
        raise
    except Exception as exc:
        _record(deps, "error", outputs={"error": f"{type(exc).__name__}: {exc}"})
        raise


async def run_ticket(
    ticket_id: int, *, agents: dict[str, Agent], audit: AuditTrail, run_id: str, entry_agent: str = "boss"
) -> dict:
    """Work one ticket as a dry run. Returns the entry agent's output plus run stats."""
    team = TeamState(run_id=run_id, ticket_id=ticket_id, audit=audit, agents=agents)
    prompt = (
        f"New ticket {ticket_id}. DRY RUN: investigate with your MCP tools, involve the specialists you "
        "need, and propose next steps for a human to approve. Nothing will be executed."
    )
    result: dict[str, Any] = {"ticket_id": ticket_id, "entry_agent": entry_agent}
    try:
        output = await run_agent(entry_agent, prompt, team)
        result.update(status="ok", output=output.model_dump())
    except AgentStopped as exc:
        result.update(status="stopped", reason=str(exc))
    except Exception as exc:
        result.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    u = team.usage
    result["usage"] = {
        "requests": u.requests, "tool_calls": u.tool_calls,
        "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
        "delegations": team.delegations,
    }
    return result
