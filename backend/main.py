"""Campus Customs backend API (HW 5, Problem 7).

Run from this folder (with the .venv active):
    uvicorn main:app --reload --port 8000
Interactive docs: http://127.0.0.1:8000/docs

Reads go through the campus-customs MCP server (the same tools the agents use).
Agent runs use the Problem 5 team unchanged. Money moves only in
POST /approvals/{id}/approve, after a human approves; ledger.py is the only code
that writes to the database, and agents can't reach it. When a run the human
started finishes successfully, the ticket is marked resolved (status only).
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.exceptions import ToolError

import ledger
from agents import build_team, run_ticket
from approvals import ApprovalStore
from audit import AuditTrail, now
from config import DB_PATH
from mcp_link import build_mcp_toolset, check_server_tools
from models import ApproveRequest


@dataclass
class State:
    mcp: Any = None
    agents: dict = field(default_factory=dict)
    audit: AuditTrail = field(default_factory=AuditTrail)
    approvals: ApprovalStore = field(default_factory=ApprovalStore)
    active_run: dict | None = None           # the run in progress, if any
    runs: dict[str, dict] = field(default_factory=dict)  # finished runs this session
    run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)    # one agent run at a time
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one approval/reset at a time


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp = build_mcp_toolset()
    async with mcp:  # one MCP server process for the routes and all five agents
        await check_server_tools(mcp)
        state.mcp, state.agents = mcp, build_team(mcp)
        yield


app = FastAPI(title="Campus Customs backend", version="1.0", lifespan=lifespan)
# The Vite dashboard (frontend/, npm run dev) runs on localhost:5173; allow local Vite ports only.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):51\d\d",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


async def call_mcp(tool: str, args: dict | None = None) -> dict:
    try:
        result = await state.mcp.client.call_tool(tool, args or {})
    except ToolError as exc:
        raise HTTPException(404, str(exc)) from exc
    return result.structured_content or result.data


def db_sha256() -> str:
    return hashlib.sha256(DB_PATH.read_bytes()).hexdigest()


# ---------- 1. tickets ----------

@app.get("/tickets")
async def list_tickets() -> dict:
    """Every ticket with whether it is open or resolved."""
    data = await call_mcp("list_tickets")
    tickets = [{**t, "is_open": t["status"] == "open", "is_resolved": t["status"] == "resolved"} for t in data["tickets"]]
    return {"today": data["today"], "tickets": tickets}


# ---------- 2. run the agent team ----------

async def _work_ticket(run_id: str, ticket_id: int) -> dict:
    try:
        result = await run_ticket(ticket_id, agents=state.agents, audit=state.audit, run_id=run_id)
        created = state.approvals.capture_from_run(run_id, ticket_id, state.audit.load())
        result["approvals_created"] = [a.model_dump() for a in created]
        result["ticket_resolved"] = False
        if result["status"] == "ok":  # the team finished its work: close the ticket (status only, no money)
            async with state.write_lock:
                result["ticket_resolved"] = await asyncio.to_thread(ledger.mark_ticket_resolved, ticket_id)
    except Exception as exc:  # run_ticket catches agent errors; this is a last resort
        result = {"ticket_id": ticket_id, "status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    result.update(run_id=run_id, finished_at=now())
    state.runs[run_id] = result
    state.active_run = None
    state.run_lock.release()
    return result


@app.post("/tickets/{ticket_id}/run", status_code=202)
async def run_agents(
    ticket_id: int, response: Response, wait: bool = Query(False, description="Wait for the run to finish.")
) -> dict:
    """Start the agent team on one ticket (dry run: agents only read and propose)."""
    ticket = (await call_mcp("get_ticket", {"ticket_id": ticket_id}))["ticket"]
    if ticket["status"] != "open":
        raise HTTPException(409, f"Ticket {ticket_id} is {ticket['status']}; only open tickets can be worked.")
    if state.run_lock.locked():
        raise HTTPException(409, f"The team is already working ticket {state.active_run['ticket_id']} "
                                 f"(run {state.active_run['run_id']}). Try again when it finishes.")
    await state.run_lock.acquire()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    state.active_run = {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "started_at": now()}
    task = asyncio.create_task(_work_ticket(run_id, ticket_id))
    if wait:
        response.status_code = 200
        return await task
    return {**state.active_run, "events_url": f"/events?run_id={run_id}"}


# ---------- 3. agent events ----------

def _said(rec: dict) -> str:
    out, inp = rec.get("outputs") or {}, rec.get("inputs") or {}
    kind = rec["step_type"]
    if kind == "task_received":
        return inp.get("prompt", "")
    if kind == "model_response":
        return out.get("text", "")
    if kind == "final_output":
        return out.get("summary") or out.get("answer") or ""
    if kind in ("guardrail", "error"):
        return out.get("stopped") or out.get("blocked") or out.get("error") or ""
    return ""


@app.get("/events")
async def events(
    since: int = Query(0, ge=0, description="Return events after this position (use next_since from the last call)."),
    limit: int = Query(200, ge=1, le=1000),
    run_id: str | None = None,
    ticket_id: int | None = None,
) -> dict:
    """Recent agent-loop steps from the audit trail: who acted, what it said, which tools it used."""
    records = state.audit.load()
    out, next_since = [], since
    for seq in range(since, len(records)):
        next_since = seq + 1
        rec = records[seq]
        if (run_id and rec["run_id"] != run_id) or (ticket_id and rec["ticket_id"] != ticket_id):
            continue
        out.append({
            "seq": seq,
            **{k: rec[k] for k in ("run_id", "timestamp", "ticket_id", "agent", "depth", "chain", "step", "step_type")},
            "said": _said(rec),
            "tools_used": [c.split(":", 1)[1] for c in rec["called"] if c.startswith("mcp:")],
            "delegated_to": [c.split(":", 1)[1] for c in rec["called"] if c.startswith("delegate:")],
            "inputs": rec["inputs"],
            "outputs": rec["outputs"],
            "usage": rec.get("usage"),
        })
        if len(out) >= limit:
            break
    return {
        "events": out,
        "next_since": next_since,
        "total_events": len(records),
        "active_run": state.active_run,
        "recent_runs": [
            {k: r.get(k) for k in ("run_id", "ticket_id", "status", "reason", "ticket_resolved", "finished_at", "usage")}
            for r in list(state.runs.values())[-5:]
        ],
    }


# ---------- 4. human approval of payments and purchases ----------

@app.get("/approvals")
async def list_approvals(status: Literal["pending", "approved", "cancelled_by_reset"] | None = None) -> dict:
    """Payments and purchases the agents prepared. Nothing here has moved money unless status is 'approved'."""
    return {"approvals": [a.model_dump() for a in state.approvals.all(status)]}


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApproveRequest) -> dict:
    """A human approves one prepared payment or purchase. This is the only place money moves."""
    async with state.write_lock:
        approval = state.approvals.get(approval_id)
        if approval is None:
            raise HTTPException(404, f"Approval {approval_id} not found.")
        if approval.status != "pending":
            raise HTTPException(409, f"Approval {approval_id} is {approval.status}; it can't be approved again.")
        policy = (await call_mcp("get_shop_policy"))["policy"]
        try:
            result = await asyncio.to_thread(
                ledger.execute_approval, approval,
                approved_by=body.approved_by, role=body.role, resolve_ticket=body.resolve_ticket, policy=policy,
            )
        except ledger.LedgerError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        updated = state.approvals.mark_approved(
            approval_id, approved_by=body.approved_by, role=body.role, payment_id=result["payment"]["id"]
        )
    return {"approval": updated.model_dump(), **result}


# ---------- 5. checking balance ----------

@app.get("/cash/checking")
async def checking_balance() -> dict:
    """Current checking balance from the cash_accounts table (via get_cash_position)."""
    data = await call_mcp("get_cash_position")
    acct = next((a for a in data["cash_accounts"] if a["name"] == "checking"), None)
    if acct is None:
        raise HTTPException(404, "No 'checking' account in cash_accounts.")
    return {"today": data["today"], **acct}


# ---------- 6. reset ----------

@app.post("/reset")
async def reset() -> dict:
    """Restore data/campus_customs_new.db from the original data/campus_customs.db and verify it."""
    if state.run_lock.locked():
        raise HTTPException(409, "An agent run is in progress; reset when it finishes.")
    async with state.write_lock:
        before = db_sha256()
        result = await asyncio.to_thread(ledger.reset_database)
        cancelled = state.approvals.cancel_pending()
    if not result["matches_original"]:
        raise HTTPException(500, {"message": "Reset did not match the original.", **result})
    return {**result, "pending_approvals_cancelled": cancelled, "sha256_before": before, "sha256_after": db_sha256()}
