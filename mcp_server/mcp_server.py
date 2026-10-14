"""Campus Customs MCP server — HW 5, Problems 3 and 5.

Tools over ../data/campus_customs_new.db, opened read-only:
  * three ticket-review tools (Problem 3), one per open ticket
  * read-only lookups for the agent team (Problem 5)
  * propose-only tools (Problem 5): they check a payment, discount, restock, or
    customer reply and return a proposal for a human to approve. They never
    write to the database, never send anything, and never move money.
Every value returned comes straight from the database; the only extra numbers
are simple arithmetic on those values (totals, shortfalls, days until due).
The one exception is SHOP_POLICY below: guardrail settings chosen for this
assignment, labelled as policy (not database facts) wherever they are returned.

Run from this folder (stdio):  python mcp_server.py
Run (HTTP):                    python mcp_server.py --http
HTTP URL:                      http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import sqlite3
import re
from datetime import date, timedelta
from pathlib import Path

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")

# Guardrail settings for the agent team. These are shop POLICY chosen for this
# assignment, not facts from the database; change them here and every agent
# sees the new values through get_shop_policy and the propose_* tools.
SHOP_POLICY = {
    "agents_can_write_data": False,
    "agents_can_move_money": False,
    "every_payment_needs_human_approval": True,
    "every_refund_needs_human_approval": True,
    "staff_approval_limit_usd": 500,      # above this, the owner must approve
    "min_cash_reserve_usd": 500,          # flag any plan that leaves less in cash
    "max_agent_discount_pct": 15,         # larger discounts need owner approval
    "never_sell_below_unit_cost": True,
    "customer_messages_are_drafts_only": True,
    "max_customer_reply_chars": 1200,
}


def _policy_block() -> dict:
    return {"source": "shop policy (guardrail settings, not database facts)", **SHOP_POLICY}


# ---------- shared helpers ----------

def _connect() -> sqlite3.Connection:
    """Open the working copy in read-only mode so these tools can never change data."""
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _today(conn: sqlite3.Connection) -> str:
    """The shop's official 'today' comes from the desk table, not the computer clock."""
    return conn.execute("SELECT date_today FROM desk").fetchone()[0]


def _days_from(today: str, other: str) -> int:
    """Days from `today` to `other` (negative means `other` is in the past)."""
    return (date.fromisoformat(other[:10]) - date.fromisoformat(today[:10])).days


def _ticket(conn: sqlite3.Connection, ticket_id: int, expected_type: str) -> dict:
    ticket = _one(conn, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found.")
    if ticket["type"] != expected_type:
        raise ValueError(
            f"Ticket {ticket_id} is type '{ticket['type']}', but this tool handles '{expected_type}'."
        )
    return ticket


# ---------- Ticket 101: white tee customer order ----------

@mcp.tool
def review_customer_order(ticket_id: int = 101) -> dict:
    """Check a customer-order ticket (default: ticket 101, white tee size S).

    Returns the ticket, stock for the requested SKU and size, stock in the other
    sizes, pricing for the order, and the linked reprint invoice with its vendor
    (amount, due date, days overdue, and vendor lead time).
    """
    with _connect() as conn:
        today = _today(conn)
        t = _ticket(conn, ticket_id, "customer_order")

        stock = _one(
            conn,
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (t["sku"], t["size"]),
        )
        other_sizes = _all(
            conn,
            "SELECT size, qty, location FROM inventory WHERE sku = ? AND size != ? ORDER BY rowid",
            (t["sku"], t["size"]),
        )
        price = _one(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (t["sku"],))

        invoice = None
        if t["invoice_id"] is not None:
            invoice = _one(conn, "SELECT * FROM invoices WHERE id = ?", (t["invoice_id"],))
            if invoice:
                invoice["days_overdue"] = max(0, -_days_from(today, invoice["due_date"]))
                invoice["vendor"] = _one(
                    conn,
                    "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?",
                    (invoice["vendor_id"],),
                )

    qty_on_hand = stock["qty"] if stock else 0
    return {
        "today": today,
        "ticket": t,
        "requested_item": {
            "sku": t["sku"],
            "name": stock["name"] if stock else None,
            "size": t["size"],
            "qty_requested": t["qty"],
            "qty_on_hand": qty_on_hand,
            "location": stock["location"] if stock else None,
            "can_fulfill_from_stock": qty_on_hand >= (t["qty"] or 0),
        },
        "other_sizes": other_sizes,
        "pricing": None if price is None else {
            **price,
            "order_revenue_at_list": price["list_price"] * t["qty"],
            "order_cost": price["unit_cost"] * t["qty"],
        },
        "linked_invoice": invoice,
    }


# ---------- Ticket 102: rent notice ----------

@mcp.tool
def review_rent_notice(ticket_id: int = 102) -> dict:
    """Check a rent-notice ticket (default: ticket 102, Chapel Street shop rent).

    Returns the ticket, the linked lease (rent amount, landlord, days until due),
    any payments already recorded for that lease, cash balances, other open
    invoices, and what cash would remain after paying rent (and those invoices).
    """
    with _connect() as conn:
        today = _today(conn)
        t = _ticket(conn, ticket_id, "rent_notice")

        lease = _one(conn, "SELECT * FROM leases WHERE id = ?", (t["lease_id"],))
        if lease is None:
            raise ValueError(f"Ticket {ticket_id} links to lease {t['lease_id']}, which does not exist.")
        lease["days_until_due"] = _days_from(today, lease["next_due"])

        lease_payments = _all(
            conn,
            "SELECT * FROM payments WHERE ref_id = ? AND kind IN ('rent', 'lease') ORDER BY paid_at",
            (lease["id"],),
        )
        all_payments_count = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        accounts = _all(conn, "SELECT name, balance, date FROM cash_accounts ORDER BY name")
        open_invoices = _all(
            conn,
            """
            SELECT i.id, i.amount, i.due_date, i.description, v.name AS vendor
            FROM invoices i JOIN vendors v ON v.id = i.vendor_id
            WHERE i.status = 'open' ORDER BY i.due_date
            """,
        )

    total_cash = sum(a["balance"] for a in accounts)
    open_invoice_total = sum(i["amount"] for i in open_invoices)
    rent = lease["monthly_rent"]
    return {
        "today": today,
        "ticket": t,
        "lease": lease,
        "payments_already_recorded_for_lease": lease_payments,
        "payments_table_row_count": all_payments_count,
        "cash_accounts": accounts,
        "total_cash": total_cash,
        "can_afford_rent": total_cash >= rent,
        "cash_after_rent": total_cash - rent,
        "open_invoices": open_invoices,
        "open_invoice_total": open_invoice_total,
        "cash_after_rent_and_open_invoices": total_cash - rent - open_invoice_total,
    }


# ---------- Ticket 103: bulk hoodie price override ----------

@mcp.tool
def review_bulk_order(ticket_id: int = 103) -> dict:
    """Check a bulk price-override ticket (default: ticket 103, 20 navy hoodies size M).

    Returns the ticket, stock for the requested size and shortfall, stock in the
    other sizes, list-price total versus cost (the break-even floor for any
    discount), and the vendors with their lead times for restocking.
    """
    with _connect() as conn:
        today = _today(conn)
        t = _ticket(conn, ticket_id, "price_override")

        stock = _one(
            conn,
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (t["sku"], t["size"]),
        )
        other_sizes = _all(
            conn,
            "SELECT size, qty, location FROM inventory WHERE sku = ? AND size != ? ORDER BY rowid",
            (t["sku"], t["size"]),
        )
        price = _one(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (t["sku"],))
        vendors = _all(conn, "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days")

    qty = t["qty"] or 0
    qty_on_hand = stock["qty"] if stock else 0
    pricing = None
    if price:
        list_total = price["list_price"] * qty
        cost_total = price["unit_cost"] * qty
        pricing = {
            **price,
            "qty": qty,
            "list_total": list_total,
            "cost_total_break_even": cost_total,
            "max_margin_at_list": list_total - cost_total,
            "max_discount_pct_before_loss": round(
                100 * (price["list_price"] - price["unit_cost"]) / price["list_price"], 1
            ),
        }
    return {
        "today": today,
        "ticket": t,
        "requested_item": {
            "sku": t["sku"],
            "name": stock["name"] if stock else None,
            "size": t["size"],
            "qty_requested": qty,
            "qty_on_hand": qty_on_hand,
            "shortfall": max(0, qty - qty_on_hand),
            "location": stock["location"] if stock else None,
        },
        "other_sizes": other_sizes,
        "pricing": pricing,
        "vendors": vendors,
    }


# ---------- Read-only lookups for the agent team (Problem 5) ----------

def _days_overdue(today: str, due: str) -> int:
    return max(0, -_days_from(today, due))


@mcp.tool
def list_open_tickets() -> dict:
    """List every open ticket (id, type, requester, subject) and the shop's 'today'."""
    with _connect() as conn:
        return {
            "today": _today(conn),
            "open_tickets": _all(
                conn,
                "SELECT id, type, requester, subject, status FROM tickets WHERE status = 'open' ORDER BY id",
            ),
        }


@mcp.tool
def list_tickets() -> dict:
    """List every ticket, open or resolved (id, type, requester, subject, status), and 'today'."""
    with _connect() as conn:
        return {
            "today": _today(conn),
            "tickets": _all(conn, "SELECT id, type, requester, subject, status FROM tickets ORDER BY id"),
        }


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Return one ticket's full row (what was asked, by whom, linked lease/invoice) and 'today'."""
    with _connect() as conn:
        ticket = _one(conn, "SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found.")
        return {"today": _today(conn), "ticket": ticket}


@mcp.tool
def get_shop_policy() -> dict:
    """Return the guardrail rules agents must follow (approval limits, cash reserve,
    discount authority, reply length) plus the shop's 'today'. These are policy
    settings, not database facts."""
    with _connect() as conn:
        return {"today": _today(conn), "policy": _policy_block()}


@mcp.tool
def check_inventory(sku: str, size: str | None = None) -> dict:
    """Stock on hand for a SKU (one size, or every size if size is omitted), with
    product name, shelf location, and the public list price. Unit cost is NOT
    included; use get_pricing for internal costs."""
    with _connect() as conn:
        rows = _all(
            conn,
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? ORDER BY rowid",
            (sku,),
        )
        if not rows:
            known = [f"{r['sku']} ({r['name']})" for r in _all(conn, "SELECT DISTINCT sku, name FROM inventory")]
            raise ValueError(f"SKU {sku!r} is not in inventory. Use a SKU code, one of: {', '.join(known)}.")
        price = _one(conn, "SELECT list_price FROM pricing WHERE sku = ?", (sku,))
    if size is not None:
        rows = [r for r in rows if r["size"].upper() == size.upper()]
        if not rows:
            raise ValueError(f"SKU {sku!r} has no size {size!r} in inventory.")
    return {
        "sku": sku,
        "list_price": price["list_price"] if price else None,
        "sizes": rows,
        "total_qty": sum(r["qty"] for r in rows),
    }


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Internal pricing for a SKU: unit cost, list price, margin per unit, and the
    largest discount possible before selling at a loss. Internal only; never share
    unit cost with customers."""
    with _connect() as conn:
        price = _one(conn, "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
    if price is None:
        raise ValueError(f"No pricing found for SKU {sku!r}.")
    margin = price["list_price"] - price["unit_cost"]
    return {
        **price,
        "margin_per_unit": margin,
        "break_even_discount_pct": round(100 * margin / price["list_price"], 2),
    }


@mcp.tool
def list_vendors() -> dict:
    """Every vendor with its specialty and lead time in days, fastest first."""
    with _connect() as conn:
        return {"vendors": _all(conn, "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days")}


def _open_invoices(conn: sqlite3.Connection, today: str) -> list[dict]:
    invoices = _all(
        conn,
        """
        SELECT i.id, i.vendor_id, v.name AS vendor, i.amount, i.due_date, i.status, i.description
        FROM invoices i JOIN vendors v ON v.id = i.vendor_id
        WHERE i.status = 'open' ORDER BY i.due_date
        """,
    )
    for inv in invoices:
        inv["days_overdue"] = _days_overdue(today, inv["due_date"])
    return invoices


def _rent_due_within(conn: sqlite3.Connection, today: str, days: int) -> list[dict]:
    leases = _all(conn, "SELECT id, space_name, landlord, monthly_rent, next_due FROM leases ORDER BY next_due")
    due = []
    for lease in leases:
        lease["days_until_due"] = _days_from(today, lease["next_due"])
        if lease["days_until_due"] <= days:
            due.append(lease)
    return due


@mcp.tool
def get_cash_position() -> dict:
    """Cash balances, open vendor invoices (with days overdue), rent due in the next
    30 days, how many payments are recorded, and the cash left if every one of those
    known bills were paid."""
    with _connect() as conn:
        today = _today(conn)
        accounts = _all(conn, "SELECT name, balance, date FROM cash_accounts ORDER BY name")
        invoices = _open_invoices(conn, today)
        rent_due = _rent_due_within(conn, today, 30)
        payments_count = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    total_cash = sum(a["balance"] for a in accounts)
    invoice_total = sum(i["amount"] for i in invoices)
    rent_total = sum(r["monthly_rent"] for r in rent_due)
    after_all = total_cash - invoice_total - rent_total
    return {
        "today": today,
        "cash_accounts": accounts,
        "total_cash": total_cash,
        "open_invoices": invoices,
        "open_invoice_total": invoice_total,
        "rent_due_next_30_days": rent_due,
        "rent_due_total": rent_total,
        "payments_recorded": payments_count,
        "cash_after_all_known_bills": after_all,
        "min_cash_reserve_usd": SHOP_POLICY["min_cash_reserve_usd"],
        "below_reserve_after_all_bills": after_all < SHOP_POLICY["min_cash_reserve_usd"],
    }


@mcp.tool
def get_invoice(invoice_id: int) -> dict:
    """One vendor invoice with its vendor, days overdue, and any payments recorded against it."""
    with _connect() as conn:
        today = _today(conn)
        inv = _one(conn, "SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        if inv is None:
            raise ValueError(f"Invoice {invoice_id} not found.")
        inv["days_overdue"] = _days_overdue(today, inv["due_date"])
        inv["vendor"] = _one(
            conn, "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (inv["vendor_id"],)
        )
        inv["payments_recorded"] = _all(
            conn, "SELECT * FROM payments WHERE kind = 'invoice' AND ref_id = ? ORDER BY paid_at", (invoice_id,)
        )
    return {"today": today, "invoice": inv}


@mcp.tool
def get_lease(lease_id: int) -> dict:
    """One lease (space, landlord, monthly rent, next due date, days until due) and
    any rent payments recorded against it."""
    with _connect() as conn:
        today = _today(conn)
        lease = _one(conn, "SELECT * FROM leases WHERE id = ?", (lease_id,))
        if lease is None:
            raise ValueError(f"Lease {lease_id} not found.")
        lease["days_until_due"] = _days_from(today, lease["next_due"])
        lease["payments_recorded"] = _all(
            conn,
            "SELECT * FROM payments WHERE ref_id = ? AND kind IN ('rent', 'lease') ORDER BY paid_at",
            (lease_id,),
        )
    return {"today": today, "lease": lease}


@mcp.tool
def list_payments(kind: str | None = None, ref_id: int | None = None) -> dict:
    """Payments already recorded, optionally filtered by kind ('rent' or 'invoice') and ref_id."""
    sql, params = "SELECT * FROM payments WHERE 1 = 1", []
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    if ref_id is not None:
        sql += " AND ref_id = ?"
        params.append(ref_id)
    with _connect() as conn:
        rows = _all(conn, sql + " ORDER BY paid_at", tuple(params))
    return {"filters": {"kind": kind, "ref_id": ref_id}, "payments": rows, "count": len(rows)}


# ---------- Propose-only tools (Problem 5): check a plan, write nothing ----------

PROPOSAL_NOTE = "PROPOSAL ONLY: nothing was written, sent, or paid. A human must approve before anything happens."


@mcp.tool
def propose_payment(kind: str, ref_id: int, amount: float, account: str = "checking") -> dict:
    """Check a proposed payment and return it for human approval. Writes nothing.

    kind: 'rent' (ref_id = lease id) or 'invoice' (ref_id = invoice id).
    Checks that the bill exists and the amount matches it, that it isn't already
    paid, that the account can cover it, the cash left afterwards (also after the
    other known bills), the cash reserve, and who must approve it.
    """
    if kind not in ("rent", "invoice"):
        raise ValueError("kind must be 'rent' or 'invoice'.")
    if amount <= 0:
        raise ValueError("amount must be greater than 0.")
    with _connect() as conn:
        today = _today(conn)
        if kind == "rent":
            bill = _one(conn, "SELECT * FROM leases WHERE id = ?", (ref_id,))
            if bill is None:
                raise ValueError(f"Lease {ref_id} not found.")
            billed, due, payee = bill["monthly_rent"], bill["next_due"], bill["landlord"]
            already = _all(
                conn, "SELECT * FROM payments WHERE ref_id = ? AND kind IN ('rent', 'lease')", (ref_id,)
            )
        else:
            bill = _one(conn, "SELECT * FROM invoices WHERE id = ?", (ref_id,))
            if bill is None:
                raise ValueError(f"Invoice {ref_id} not found.")
            billed, due = bill["amount"], bill["due_date"]
            payee = _one(conn, "SELECT name FROM vendors WHERE id = ?", (bill["vendor_id"],))["name"]
            already = _all(conn, "SELECT * FROM payments WHERE kind = 'invoice' AND ref_id = ?", (ref_id,))
        acct = _one(conn, "SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,))
        if acct is None:
            raise ValueError(f"Cash account {account!r} not found.")
        other_invoices = [
            i for i in _open_invoices(conn, today) if not (kind == "invoice" and i["id"] == ref_id)
        ]
        other_rent = [
            r for r in _rent_due_within(conn, today, 30) if not (kind == "rent" and r["id"] == ref_id)
        ]

    cash_after = acct["balance"] - amount
    other_total = sum(i["amount"] for i in other_invoices) + sum(r["monthly_rent"] for r in other_rent)
    reserve = SHOP_POLICY["min_cash_reserve_usd"]
    checks = {
        "amount_matches_bill": amount == billed,
        "bill_still_open": kind == "rent" or bill["status"] == "open",
        "not_already_paid": not already,
        "account_can_cover": acct["balance"] >= amount,
        "reserve_kept_after_this_payment": cash_after >= reserve,
        "reserve_kept_after_other_known_bills": cash_after - other_total >= reserve,
    }
    blocked = not (checks["account_can_cover"] and checks["not_already_paid"] and checks["bill_still_open"])
    return {
        "today": today,
        "status": "blocked" if blocked else "awaiting_human_approval",
        "note": PROPOSAL_NOTE,
        "proposed_payment_row": {
            "kind": kind, "ref_id": ref_id, "amount": amount, "account": account,
            "paid_at": None, "approved_by": None,
        },
        "payee": payee,
        "billed_amount": billed,
        "due_date": due,
        "days_until_due": _days_from(today, due),
        "account_balance": acct["balance"],
        "cash_after_this_payment": cash_after,
        "other_known_bills": {"open_invoices": other_invoices, "rent_due_next_30_days": other_rent},
        "cash_after_this_and_other_known_bills": cash_after - other_total,
        "checks": checks,
        "approval_required_from": "owner" if amount > SHOP_POLICY["staff_approval_limit_usd"] else "staff",
        "policy": _policy_block(),
    }


@mcp.tool
def propose_discount(sku: str, qty: int, discount_pct: float, size: str | None = None) -> dict:
    """Check a proposed discount and return it for human approval. Writes nothing.

    Computes the discounted unit price and total, the cost floor, the margin left,
    whether it would sell below cost (blocked), whether it exceeds the agents'
    discount authority (owner approval), and, if size is given, stock and shortfall.
    """
    if qty <= 0:
        raise ValueError("qty must be greater than 0.")
    if not 0 <= discount_pct < 100:
        raise ValueError("discount_pct must be between 0 and 100.")
    with _connect() as conn:
        today = _today(conn)
        price = _one(conn, "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,))
        if price is None:
            raise ValueError(f"No pricing found for SKU {sku!r}.")
        stock = None
        if size is not None:
            stock = _one(conn, "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size))
            if stock is None:
                raise ValueError(f"SKU {sku!r} has no size {size!r} in inventory.")

    unit_price = round(price["list_price"] * (1 - discount_pct / 100), 2)
    total = round(unit_price * qty, 2)
    cost_total = price["unit_cost"] * qty
    below_cost = unit_price < price["unit_cost"]
    over_authority = discount_pct > SHOP_POLICY["max_agent_discount_pct"]
    result = {
        "today": today,
        "status": "blocked_below_cost" if below_cost else "awaiting_human_approval",
        "note": PROPOSAL_NOTE,
        "sku": sku,
        "qty": qty,
        "discount_pct": discount_pct,
        "list_price": price["list_price"],
        "discounted_unit_price": unit_price,
        "list_total": price["list_price"] * qty,
        "discounted_total": total,
        "customer_saves": round(price["list_price"] * qty - total, 2),
        "unit_cost": price["unit_cost"],
        "cost_total": cost_total,
        "margin_after_discount": round(total - cost_total, 2),
        "below_cost": below_cost,
        "exceeds_agent_discount_authority": over_authority,
        "approval_required_from": "owner" if over_authority else "staff",
        "policy": _policy_block(),
    }
    if stock is not None:
        result["stock"] = {
            "size": size, "qty_on_hand": stock["qty"], "shortfall": max(0, qty - stock["qty"]),
        }
    return result


@mcp.tool
def propose_restock(sku: str, size: str, qty: int, vendor_id: int) -> dict:
    """Check a proposed restock order and return it for human approval. Writes nothing.

    Returns current stock, the vendor's specialty and lead time, the earliest arrival
    date, an estimated cost at the catalog unit cost (the vendor's real quote may
    differ), cash on hand, and any open invoice that already mentions this SKU and size.
    """
    if qty <= 0:
        raise ValueError("qty must be greater than 0.")
    with _connect() as conn:
        today = _today(conn)
        stock = _one(
            conn, "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        )
        if stock is None:
            raise ValueError(f"SKU {sku!r} has no size {size!r} in inventory.")
        vendor = _one(conn, "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,))
        if vendor is None:
            raise ValueError(f"Vendor {vendor_id} not found.")
        price = _one(conn, "SELECT unit_cost FROM pricing WHERE sku = ?", (sku,))
        total_cash = conn.execute("SELECT COALESCE(SUM(balance), 0) FROM cash_accounts").fetchone()[0]
        related = [
            inv for inv in _open_invoices(conn, today)
            if sku in (inv["description"] or "") and size in (inv["description"] or "").split()
        ]
    estimate = price["unit_cost"] * qty if price else None
    return {
        "today": today,
        "status": "awaiting_human_approval",
        "note": PROPOSAL_NOTE,
        "item": stock,
        "qty_to_order": qty,
        "vendor": vendor,
        "earliest_arrival": (date.fromisoformat(today) + timedelta(days=vendor["lead_days"])).isoformat(),
        "estimated_cost_at_unit_cost": estimate,
        "estimate_note": "Catalog unit cost x qty; the vendor's actual quote may differ.",
        "total_cash": total_cash,
        "related_open_invoices": related,
        "approval_required_from": (
            "owner" if estimate is not None and estimate > SHOP_POLICY["staff_approval_limit_usd"] else "staff"
        ),
        "policy": _policy_block(),
    }


def _money_forms(value: float, dollar_sign_only: bool) -> set[str]:
    forms = {f"${value:,.2f}", f"${value:,.0f}", f"${value:.0f}"}
    if not dollar_sign_only:
        forms |= {f"{value:,.0f}", f"{value:.0f}"}
    return forms


@mcp.tool
def propose_customer_reply(ticket_id: int, message: str) -> dict:
    """Check a draft customer reply and return it for human review. Sends nothing.

    Flags: the reply is over the length cap; it mentions internal figures (unit costs,
    cash balances, invoice or rent amounts); it uses internal-only words (invoice,
    margin, rent...); or it names another ticket's requester (privacy).
    """
    with _connect() as conn:
        ticket = _one(conn, "SELECT id, requester, type FROM tickets WHERE id = ?", (ticket_id,))
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found.")
        internal = {}
        for r in conn.execute("SELECT sku, unit_cost FROM pricing"):
            internal.update({f: f"unit cost of {r[0]}" for f in _money_forms(r[1], dollar_sign_only=True)})
        for r in conn.execute("SELECT name, balance FROM cash_accounts"):
            internal.update({f: f"{r[0]} balance" for f in _money_forms(r[1], dollar_sign_only=False)})
        for r in conn.execute("SELECT id, amount FROM invoices"):
            internal.update({f: f"invoice {r[0]} amount" for f in _money_forms(r[1], dollar_sign_only=False)})
        for r in conn.execute("SELECT space_name, monthly_rent FROM leases"):
            internal.update({f: f"rent for {r[0]}" for f in _money_forms(r[1], dollar_sign_only=False)})
        others = [
            r[0] for r in conn.execute("SELECT DISTINCT requester FROM tickets WHERE id != ?", (ticket_id,))
        ]

    def mentions(token: str) -> bool:
        # whole-token match so "$28" does not match "$280" and "840" does not match "1840"
        return re.search(rf"(?<![\w$.,]){re.escape(token)}(?![\w]|[.,]\d)", message) is not None

    internal_hits = sorted({label for token, label in internal.items() if mentions(token)})
    word_hits = sorted(
        w for w in ("unit cost", "our cost", "invoice", "margin", "rent", "landlord", "cash balance", "checking account")
        if re.search(rf"\b{w}\b", message, re.IGNORECASE)
    )
    name_hits = [n for n in others if n.lower() in message.lower()]
    max_chars = SHOP_POLICY["max_customer_reply_chars"]
    issues = []
    if len(message) > max_chars:
        issues.append(f"Reply is {len(message)} characters; the cap is {max_chars}.")
    if internal_hits:
        issues.append("Mentions internal figures: " + ", ".join(internal_hits) + ".")
    if word_hits:
        issues.append("Uses internal-only words: " + ", ".join(word_hits) + ".")
    if name_hits:
        issues.append("Names another customer or requester: " + ", ".join(name_hits) + ".")
    return {
        "status": "needs_revision" if issues else "draft_awaiting_human_review",
        "note": "DRAFT ONLY: nothing was sent. A human must review and send it.",
        "ticket_id": ticket_id,
        "to": ticket["requester"],
        "message": message,
        "chars": len(message),
        "issues": issues,
        "policy": _policy_block(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on port 8001 (keeps FastAPI free on 8000)",
    )
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=8001)
    else:
        mcp.run(show_banner=False)  # keep the agents' console output readable
