"""Pending approvals: payments and purchases the agents prepared, waiting for a human.

After a run, capture_from_run() reads that run's audit records and keeps every
propose_payment / propose_restock result whose status is awaiting_human_approval.
The amounts come from the MCP tool's checked output, never from the model's own
text. Approvals are stored in output/approvals.json (same atomic-write pattern as
the audit trail). Identical pending proposals are kept once.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from audit import now
from config import PROJECT_ROOT
from models import Approval

APPROVALS_PATH = PROJECT_ROOT / "output" / "approvals.json"


def _from_payment(content: dict) -> dict:
    row = content["proposed_payment_row"]
    return {
        "type": "payment",
        "payment_kind": row["kind"],
        "ref_id": row["ref_id"],
        "amount": row["amount"],
        "account": row["account"],
        "payee": content["payee"],
        "approval_required_from": content["approval_required_from"],
        "details": {
            k: content.get(k)
            for k in ("due_date", "days_until_due", "billed_amount", "account_balance", "cash_after_this_payment",
                      "cash_after_this_and_other_known_bills", "checks")
        },
    }


def _from_restock(content: dict) -> dict:
    item, vendor = content["item"], content["vendor"]
    return {
        "type": "purchase",
        "payment_kind": "restock",
        "ref_id": vendor["id"],
        "amount": content["estimated_cost_at_unit_cost"],
        "account": "checking",
        "payee": vendor["name"],
        "approval_required_from": content["approval_required_from"],
        "details": {
            "sku": item["sku"], "size": item["size"], "name": item["name"], "qty_on_hand": item["qty"],
            "qty_to_order": content["qty_to_order"], "vendor": vendor,
            "earliest_arrival": content["earliest_arrival"], "estimate_note": content["estimate_note"],
            "related_open_invoices": content.get("related_open_invoices", []),
        },
    }


PARSERS = {"propose_payment": _from_payment, "propose_restock": _from_restock}


def _signature(a: dict) -> tuple:
    d = a["details"]
    return (a["payment_kind"], a["ref_id"], a["amount"], a["account"], d.get("sku"), d.get("size"), d.get("qty_to_order"))


class ApprovalStore:
    def __init__(self, path: Path = APPROVALS_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, records: list[dict]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        for attempt in range(5):  # OneDrive can briefly lock the file while syncing
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)

    def all(self, status: str | None = None) -> list[Approval]:
        return [Approval(**r) for r in self._load() if status is None or r["status"] == status]

    def get(self, approval_id: str) -> Approval | None:
        return next((a for a in self.all() if a.id == approval_id), None)

    def capture_from_run(self, run_id: str, ticket_id: int, audit_records: list[dict]) -> list[Approval]:
        """Turn this run's awaiting-approval proposals into pending approvals."""
        records = self._load()
        pending = {_signature(r) for r in records if r["status"] == "pending"}
        created = []
        for rec in audit_records:
            if rec["run_id"] != run_id or rec["step_type"] != "tool_results":
                continue
            for out in rec["outputs"] or []:
                parse, content = PARSERS.get(out.get("tool")), out.get("content")
                if not parse or not isinstance(content, dict) or content.get("status") != "awaiting_human_approval":
                    continue
                fields = parse(content)
                if _signature(fields) in pending:
                    continue
                approval = Approval(
                    id=f"AP-{len(records) + 1:04d}", created_at=now(), run_id=run_id,
                    ticket_id=ticket_id, proposed_by=rec["agent"], **fields,
                )
                records.append(approval.model_dump())
                pending.add(_signature(fields))
                created.append(approval)
        if created:
            self._save(records)
        return created

    def mark_approved(self, approval_id: str, *, approved_by: str, role: str, payment_id: int) -> Approval:
        records = self._load()
        for r in records:
            if r["id"] == approval_id:
                r.update(status="approved", approved_by=approved_by, approver_role=role,
                         approved_at=now(), payment_id=payment_id)
                self._save(records)
                return Approval(**r)
        raise KeyError(approval_id)

    def cancel_pending(self) -> int:
        """After a database reset, pending approvals describe data that no longer exists."""
        records = self._load()
        count = 0
        for r in records:
            if r["status"] == "pending":
                r["status"] = "cancelled_by_reset"
                count += 1
        if count:
            self._save(records)
        return count
