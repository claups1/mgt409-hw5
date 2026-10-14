"""Data types shared by the Campus Customs agent team.

Agent answers are structured (SpecialistReport, TicketDecision) so the backend
and dashboard can read them reliably. Text fields have length caps; an answer
that runs too long fails validation and the agent is asked to shorten it.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]

AGENT_TITLES: dict[str, str] = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}

Short = Annotated[str, Field(max_length=400)]


class Proposal(BaseModel):
    """One action the team recommends. Nothing here has been executed."""

    kind: Literal["payment", "refund", "discount", "restock", "customer_reply", "hold", "other"]
    summary: Short = Field(description="What would happen, with the key numbers.")
    amount_usd: float | None = Field(default=None, description="Money involved, if any.")
    requires_human_approval: bool = Field(default=True, description="Payments, refunds, discounts, orders, and replies always do.")
    approver: Literal["staff", "owner", "none"] = Field(default="staff", description="From the propose_* tool or shop policy.")
    source_tool: str = Field(max_length=60, description="MCP tool whose output backs this proposal.")

    @field_validator("source_tool")
    @classmethod
    def _must_be_mcp_tool(cls, value: str) -> str:
        if value.startswith("ask_"):
            raise ValueError("source_tool must be the MCP tool behind the numbers (e.g. propose_payment), not an ask_ tool.")
        return value


class SpecialistReport(BaseModel):
    """What a specialist sends back to whoever delegated to it."""

    agent: AgentName
    ticket_id: int
    answer: Annotated[str, Field(max_length=800)] = Field(description="Direct answer to the request, in plain language.")
    facts: list[Short] = Field(default_factory=list, max_length=8, description="Each fact ends with its MCP tool, e.g. '(check_inventory)'.")
    proposals: list[Proposal] = Field(default_factory=list, max_length=4)
    risks: list[Short] = Field(default_factory=list, max_length=5)
    unresolved: list[Short] = Field(default_factory=list, max_length=4, description="What you could not confirm, and why.")


class TicketDecision(BaseModel):
    """The Boss's final plan for one ticket, ready for a human to review."""

    ticket_id: int
    ticket_type: str = Field(max_length=40)
    status: Literal["ready_for_human_review", "needs_more_info", "blocked"]
    summary: Annotated[str, Field(max_length=900)] = Field(description="What is going on and what the team recommends.")
    key_facts: list[Short] = Field(default_factory=list, max_length=10, description="Each fact ends with its MCP tool.")
    recommended_actions: list[Proposal] = Field(default_factory=list, max_length=6)
    customer_reply_draft: Annotated[str, Field(max_length=1200)] | None = Field(
        default=None, description="Only for customer tickets; must have passed propose_customer_reply."
    )
    human_approvals_needed: list[Short] = Field(default_factory=list, max_length=6)
    agents_consulted: list[AgentName] = Field(default_factory=list)
    risks: list[Short] = Field(default_factory=list, max_length=5)


class Approval(BaseModel):
    """A payment or purchase an agent prepared (via propose_payment / propose_restock),
    waiting for a human. Money moves only when a human approves it."""

    id: str
    created_at: str
    run_id: str
    ticket_id: int
    proposed_by: AgentName
    type: Literal["payment", "purchase"]
    payment_kind: Literal["rent", "invoice", "restock"]  # becomes payments.kind
    ref_id: int  # lease id (rent), invoice id (invoice), or vendor id (restock)
    amount: float
    account: str
    payee: str
    approval_required_from: Literal["staff", "owner"]
    details: dict = Field(default_factory=dict, description="The MCP tool's checks and context.")
    status: Literal["pending", "approved", "cancelled_by_reset"] = "pending"
    approved_by: str | None = None
    approver_role: Literal["staff", "owner"] | None = None
    approved_at: str | None = None
    payment_id: int | None = None


class ApproveRequest(BaseModel):
    """Body for POST /approvals/{id}/approve. The human's name goes into payments.approved_by."""

    approved_by: str = Field(min_length=1, max_length=60, description="Name of the person approving.")
    role: Literal["staff", "owner"] = Field(description="Staff may approve up to the policy limit; above it needs the owner.")
    resolve_ticket: bool = Field(default=False, description="Also mark the ticket resolved.")


class AuditRecord(BaseModel):
    """One agent-loop step, appended to output/audit_trail.json."""

    run_id: str
    timestamp: str
    ticket_id: int
    agent: AgentName
    depth: int = Field(description="0 = the agent that received the ticket; 1+ = delegated to.")
    chain: list[AgentName] = Field(description="Who delegated to whom to reach this agent.")
    step: int = Field(description="Step number inside this agent's own loop.")
    step_type: Literal[
        "task_received", "model_request", "tool_results", "model_response",
        "final_output", "guardrail", "error",
    ]
    called: list[str] = Field(default_factory=list, description="'mcp:<tool>' or 'delegate:<agent>'.")
    inputs: Any = None
    outputs: Any = None
    usage: dict | None = None
