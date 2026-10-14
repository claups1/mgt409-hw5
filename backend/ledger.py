"""The only code that changes the shop database, and only when a human asks.

Agents can't reach this module: it isn't an MCP tool or an agent tool. It is
called by main.py:
  * execute_approval(): a human approved a payment or purchase. Money moves here.
  * mark_ticket_resolved(): a run the human started finished; ticket status only.
  * reset_database(): copy the original database back over the working copy.

Double-payment protection (all checked inside one locked transaction, so two
clicks at the same moment can't both pay):
  * the approval id is written into payments.approved_by, and an approval whose
    id is already there is refused;
  * rent is paid only if the lease's next_due still equals the due date that was
    proposed (paying it moves next_due forward one month);
  * an invoice is paid only while its status is 'open' (paying marks it 'paid').
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date

from config import DB_PATH, PROJECT_ROOT
from models import Approval

ORIGINAL_DB_PATH = PROJECT_ROOT / "data" / "campus_customs.db"  # never written


class LedgerError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def _add_month(iso_day: str) -> str:
    d = date.fromisoformat(iso_day)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1])).isoformat()


def execute_approval(approval: Approval, *, approved_by: str, role: str, resolve_ticket: bool, policy: dict) -> dict:
    """Re-check the proposal against current data, then record the payment and move the money."""
    marker = f"[approval {approval.id}]"
    conn = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")  # one writer at a time
        one = lambda sql, p=(): conn.execute(sql, p).fetchone()
        today = one("SELECT date_today FROM desk")[0]

        if one("SELECT id FROM payments WHERE approved_by LIKE ?", (f"%{marker}%",)):
            raise LedgerError(409, f"Approval {approval.id} was already paid.")

        amount, kind = approval.amount, approval.payment_kind
        lease_next_due = None
        if kind == "rent":
            lease = one("SELECT * FROM leases WHERE id = ?", (approval.ref_id,))
            if lease is None:
                raise LedgerError(404, f"Lease {approval.ref_id} not found.")
            if lease["next_due"] != approval.details.get("due_date"):
                raise LedgerError(409, f"Rent due {approval.details.get('due_date')} is no longer outstanding "
                                       f"(lease next due is now {lease['next_due']}); it was probably already paid.")
            if amount != lease["monthly_rent"]:
                raise LedgerError(409, f"Amount {amount} doesn't match the rent of {lease['monthly_rent']}.")
            lease_next_due = _add_month(lease["next_due"])
        elif kind == "invoice":
            inv = one("SELECT * FROM invoices WHERE id = ?", (approval.ref_id,))
            if inv is None:
                raise LedgerError(404, f"Invoice {approval.ref_id} not found.")
            if inv["status"] != "open" or one("SELECT id FROM payments WHERE kind = 'invoice' AND ref_id = ?", (inv["id"],)):
                raise LedgerError(409, f"Invoice {inv['id']} is not open (status {inv['status']}); it was already paid.")
            if amount != inv["amount"]:
                raise LedgerError(409, f"Amount {amount} doesn't match invoice {inv['id']} ({inv['amount']}).")

        acct = one("SELECT * FROM cash_accounts WHERE name = ?", (approval.account,))
        if acct is None:
            raise LedgerError(404, f"Cash account {approval.account!r} not found.")
        if acct["balance"] < amount:
            raise LedgerError(409, f"{approval.account} has {acct['balance']}, not enough for {amount}.")
        balance_after = acct["balance"] - amount

        owner_reasons = []
        if amount > policy["staff_approval_limit_usd"]:
            owner_reasons.append(f"amount is over the ${policy['staff_approval_limit_usd']} staff limit")
        if balance_after < policy["min_cash_reserve_usd"]:
            owner_reasons.append(f"cash would fall below the ${policy['min_cash_reserve_usd']} reserve")
        if approval.approval_required_from == "owner":
            owner_reasons.append("the proposal requires the owner")
        if owner_reasons and role != "owner":
            raise LedgerError(403, "Owner approval required: " + "; ".join(owner_reasons) + ".")

        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, approval.ref_id, amount, approval.account, today, f"{approved_by} ({role}) {marker}"),
        )
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (balance_after, today, approval.account))
        if kind == "rent":
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (lease_next_due, approval.ref_id))
        elif kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (approval.ref_id,))
        # restock purchases change no stock: goods arrive after the vendor's lead time
        if resolve_ticket:
            conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (approval.ticket_id,))
        conn.execute("COMMIT")

        payment = dict(one("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)))
        return {
            "payment": payment,
            "account": approval.account,
            "balance_before": acct["balance"],
            "balance_after": balance_after,
            "lease_next_due": lease_next_due,
            "ticket_status": one("SELECT status FROM tickets WHERE id = ?", (approval.ticket_id,))[0],
        }
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def mark_ticket_resolved(ticket_id: int) -> bool:
    """Set an open ticket to 'resolved' (after a run a human started finishes). Touches no money."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        with conn:
            cur = conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ? AND status = 'open'", (ticket_id,))
        return cur.rowcount == 1
    finally:
        conn.close()


def _snapshot(conn: sqlite3.Connection) -> dict:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    return {
        "schema": conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall(),
        "rows": {t: conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables},
    }


def compare_to_original() -> dict:
    """Schema and every row of the working copy versus the original."""
    src = sqlite3.connect(f"file:{ORIGINAL_DB_PATH.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        a, b = _snapshot(src), _snapshot(dst)
    finally:
        src.close()
        dst.close()
    tables = sorted(set(a["rows"]) | set(b["rows"]))
    different = [t for t in tables if a["rows"].get(t) != b["rows"].get(t)]
    return {
        "matches_original": a["schema"] == b["schema"] and not different,
        "schema_matches": a["schema"] == b["schema"],
        "tables_different": different,
        "row_counts": {t: len(b["rows"].get(t, [])) for t in tables},
    }


def reset_database() -> dict:
    """Copy the original database over the working copy (SQLite backup API), then verify."""
    src = sqlite3.connect(f"file:{ORIGINAL_DB_PATH.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(DB_PATH, timeout=10)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return compare_to_original()
