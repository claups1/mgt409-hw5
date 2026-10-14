"""Offline guardrail tests: no API calls, no Portkey spend.

Fake models (PydanticAI FunctionModel) stand in for gpt-6-luna:
  1. Greedy delegation: every agent delegates to every agent it is offered.
     Checks the loop guard, the depth limit, and the per-ticket hand-off budget.
  2. Endless tool calls: an agent that never stops calling a tool.
     Checks the per-agent step cap.
The real MCP server is used (read-only). Records go to a temporary audit file,
so output/audit_trail.json is not touched.

    cd backend
    .venv\\Scripts\\python.exe test_guardrails.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

os.environ.setdefault("PORTKEY_API_KEY", "offline-test")  # fake models never call Portkey

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

import agents as A
from audit import AuditTrail
from mcp_link import build_mcp_toolset

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def greedy(messages, info):
    """First turn: call every ask_ tool offered. Then return a minimal valid answer."""
    offered = [t.name for t in info.function_tools if t.name.startswith("ask_")]
    already = any(isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", []))
    if offered and not already:
        return ModelResponse(parts=[ToolCallPart(n, {"request": "please help"}) for n in offered])
    out = info.output_tools[0]
    if "agent" in out.parameters_json_schema["properties"]:  # SpecialistReport
        args = {"agent": "inventory", "ticket_id": 101, "answer": "test"}
    else:  # TicketDecision
        args = {"ticket_id": 101, "ticket_type": "test", "status": "needs_more_info", "summary": "test"}
    return ModelResponse(parts=[ToolCallPart(out.name, args)])


def forever(messages, info):
    """Never answers; keeps calling an MCP tool."""
    return ModelResponse(parts=[ToolCallPart("get_shop_policy", {})])


async def greedy_test(mcp, audit: AuditTrail, entry: str) -> None:
    print(f"\nGreedy delegation, entry agent = {entry}")
    team = A.build_team(mcp)
    run_id = f"guard-{entry}"
    with ExitStack() as stack:
        for agent in team.values():
            stack.enter_context(agent.override(model=FunctionModel(greedy)))
        res = await A.run_ticket(101, agents=team, audit=audit, run_id=run_id, entry_agent=entry)
    recs = [r for r in audit.load() if r["run_id"] == run_id]
    runs = [" -> ".join(r["chain"]) for r in recs if r["step_type"] == "task_received"]
    print(f"  agent runs: {runs}")
    check("run finished", res["status"] == "ok")
    check(f"depth never above {A.MAX_DELEGATION_DEPTH}", max(r["depth"] for r in recs) == A.MAX_DELEGATION_DEPTH)
    check("no agent appears twice in a chain", all(len(set(r["chain"])) == len(r["chain"]) for r in recs))
    check(f"hand-offs capped at {A.MAX_DELEGATIONS_PER_TICKET}", res["usage"]["delegations"] == A.MAX_DELEGATIONS_PER_TICKET)
    check("extra hand-offs were blocked and audited", any(r["step_type"] == "guardrail" for r in recs))
    deepest = [r for r in recs if r["step_type"] == "model_response" and r["depth"] == A.MAX_DELEGATION_DEPTH]
    check("agents at max depth are offered no ask_ tools",
          all(not any(c.startswith("delegate:") for c in r["called"]) for r in deepest))


async def step_cap_test(mcp, audit: AuditTrail) -> None:
    print("\nEndless tool calls, Facilities")
    team = A.build_team(mcp)
    with team["facilities"].override(model=FunctionModel(forever)):
        res = await A.run_ticket(102, agents=team, audit=audit, run_id="step-cap", entry_agent="facilities")
    recs = [r for r in audit.load() if r["run_id"] == "step-cap"]
    print(f"  {res.get('reason')}")
    check("run was stopped", res["status"] == "stopped")
    check(f"stopped at the {A.MAX_STEPS_PER_AGENT}-step cap", recs[-1]["step_type"] == "guardrail"
          and recs[-1]["step"] == A.MAX_STEPS_PER_AGENT + 1)


async def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        audit = AuditTrail(Path(tmp) / "guardrail_test_audit.json")
        mcp = build_mcp_toolset()
        async with mcp:
            await greedy_test(mcp, audit, "boss")
            await greedy_test(mcp, audit, "facilities")  # also exercises ask_boss
            await step_cap_test(mcp, audit)
    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(main()))
