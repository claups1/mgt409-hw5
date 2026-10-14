"""Dry run: let the agent team work the open tickets and propose what to do.

Every tool the agents can reach is read-only or propose-only, so nothing is
paid, sent, or written. This script also proves it: it hashes the database
before and after, and reports how many audit records the run added.

    cd backend
    .venv\\Scripts\\python.exe run_tickets.py                 # tickets 101 102 103
    .venv\\Scripts\\python.exe run_tickets.py --tickets 102   # just one
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import datetime

from agents import AGENT_NAMES, build_team, run_ticket
from audit import AuditTrail
from config import AUDIT_PATH, DB_PATH, MODEL_NAME
from mcp_link import build_mcp_toolset, check_server_tools


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main(tickets: list[int], entry_agent: str) -> int:
    audit = AuditTrail()
    db_before, audit_before = sha256(DB_PATH), audit.count()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    print(f"DRY RUN {run_id} | model {MODEL_NAME} | entry agent {entry_agent} | tickets {tickets}")

    mcp = build_mcp_toolset()
    results = []
    async with mcp:  # one MCP server process shared by all five agents
        tools = await check_server_tools(mcp)
        print(f"MCP server connected: {len(tools)} tools")
        agents = build_team(mcp)
        for ticket_id in tickets:
            print(f"\n=== Ticket {ticket_id} ===")
            result = await run_ticket(ticket_id, agents=agents, audit=audit, run_id=run_id, entry_agent=entry_agent)
            results.append(result)
            print(json.dumps(result, indent=2, ensure_ascii=False))

    db_after, audit_after = sha256(DB_PATH), audit.count()
    print("\n=== Checks ===")
    print(f"Audit trail: {audit_before} -> {audit_after} records (+{audit_after - audit_before}) in {AUDIT_PATH.name}")
    print(f"Database unchanged: {db_before == db_after} (sha256 {db_after[:16]}...)")
    for r in results:
        print(f"Ticket {r['ticket_id']}: {r['status']} | {r['usage']}")
    ok = db_before == db_after and audit_after > audit_before and all(r["status"] == "ok" for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs agent team dry run")
    parser.add_argument("--tickets", type=int, nargs="+", default=[101, 102, 103])
    parser.add_argument("--entry-agent", choices=AGENT_NAMES, default="boss")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    raise SystemExit(asyncio.run(main(args.tickets, args.entry_agent)))
