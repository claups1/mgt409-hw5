# Campus Customs MCP Server

## Purpose

This is a small **FastMCP** server that gives AI agents (and your vibe coder) safe, structured access to the Campus Customs shop database. It is the agent team's **only** source of shop facts. An agent calls a tool and gets back the facts it needs to make a decision. It doesn't have to write SQL or guess at numbers.

It has **18 tools** in three groups:
- **Ticket reviews (3):** one overview per open ticket (Problem 3).
- **Read-only lookups (11):** focused questions for each specialist agent (Problem 5), plus `list_tickets` for the backend API (Problem 7).
- **Propose-only (4):** check a payment, discount, restock order, or customer reply and return it as a proposal for a human to approve (Problem 5).

**Nothing can change the data.** Every tool opens the database in SQLite read-only mode, so none of them can change, add, or delete data. The propose-only tools never pay, order, or send anything. They return what *would* happen (for example, the payment row with `approved_by: null`) and say who must approve it. Every value comes straight from the database. The only extra numbers are simple arithmetic on those values, such as totals, shortfalls, break-even cost, and days until a bill is due.

**Shop policy.** The guardrail settings (approval limits, cash reserve, discount authority, reply length cap) are defined once in `SHOP_POLICY` at the top of `mcp_server.py`. They are policy chosen for this assignment, not database facts, and every tool that returns them labels them that way.

## Database

- **File:** `../data/campus_customs_new.db` (the working copy, resolved relative to this folder)
- The original `../data/campus_customs.db` is never touched.
- "Today" is read from the `desk.date_today` field (2026-08-31), not the computer clock, so due dates are judged the same way every time.

## Tools

### Ticket reviews (read-only)

| Tool | Tables read | What it returns |
|---|---|---|
| `review_customer_order(ticket_id=101)` | `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `desk` | Stock for the requested size (and the other sizes), list price and cost, and the linked reprint invoice with amount, due date, days overdue, and the vendor's lead time. |
| `review_rent_notice(ticket_id=102)` | `tickets`, `leases`, `payments`, `cash_accounts`, `invoices`, `vendors`, `desk` | Lease details and days until rent is due, any payments already recorded for the lease, cash balances, other open invoices, and cash left after rent (and after those invoices). |
| `review_bulk_order(ticket_id=103)` | `tickets`, `inventory`, `pricing`, `vendors`, `desk` | Stock and shortfall for the requested size, stock in the other sizes, list total versus cost total (the break-even floor), the largest discount possible before a loss, and the vendors with lead times. |

Each review tool takes an optional `ticket_id`. It checks that the ticket exists and is the right type (`customer_order`, `rent_notice`, or `price_override`). If not, it returns a clear error instead of wrong data.

### Read-only lookups

| Tool | Tables read | What it returns |
|---|---|---|
| `list_open_tickets()` | `tickets`, `desk` | Every open ticket (id, type, requester, subject) and today's date. |
| `list_tickets()` | `tickets`, `desk` | Every ticket, open or resolved, with its status (used by `GET /tickets`). |
| `get_ticket(ticket_id)` | `tickets`, `desk` | One ticket's full row, including the SKU/size/qty and linked lease or invoice. |
| `get_shop_policy()` | `desk` (+ `SHOP_POLICY` settings) | The guardrail rules and today's date. |
| `check_inventory(sku, size=None)` | `inventory`, `pricing` (list price only) | Stock and location for one size or every size, plus the public list price. No unit cost. |
| `get_pricing(sku)` | `pricing` | Unit cost, list price, margin per unit, and the break-even discount %. Internal only. |
| `list_vendors()` | `vendors` | Every vendor's specialty and lead time, fastest first. |
| `get_cash_position()` | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` | Balances, open invoices with days overdue, rent due within 30 days, and cash left after all known bills, compared with the cash reserve. |
| `get_invoice(invoice_id)` | `invoices`, `vendors`, `payments`, `desk` | One invoice with its vendor, days overdue, and payments recorded against it. |
| `get_lease(lease_id)` | `leases`, `payments`, `desk` | One lease with days until rent is due and rent payments recorded. |
| `list_payments(kind=None, ref_id=None)` | `payments` | Payments already recorded, optionally filtered. |

### Propose-only (write nothing, need human approval)

| Tool | Tables read | What it checks and returns |
|---|---|---|
| `propose_payment(kind, ref_id, amount, account="checking")` | `leases` or `invoices`, `vendors`, `payments`, `cash_accounts`, `desk` | Whether the bill exists, the amount matches, it's still open and not already paid, and the account can cover it. Also cash left after this payment and after the other known bills, the reserve check, and the approver (staff or owner). Status `awaiting_human_approval` or `blocked`. |
| `propose_discount(sku, qty, discount_pct, size=None)` | `pricing`, `inventory` (if size given), `desk` | Discounted unit price and total, the margin left, a below-cost block, whether the discount exceeds agent authority (owner approval), and stock/shortfall. Status `awaiting_human_approval` or `blocked_below_cost`. |
| `propose_restock(sku, size, qty, vendor_id)` | `inventory`, `vendors`, `pricing`, `cash_accounts`, `invoices`, `desk` | Current stock, the vendor's specialty and lead time, the earliest arrival date, an estimated cost at catalog unit cost, and any **open invoice that already mentions this SKU and size** (to avoid duplicate orders). |
| `propose_customer_reply(ticket_id, message)` | `tickets`, `pricing`, `cash_accounts`, `invoices`, `leases` | A draft reply checked for the length cap, internal figures (unit costs, balances, invoice and rent amounts), internal-only words, and other customers' names. Status `draft_awaiting_human_review` or `needs_revision`. Never sent. |

Tools return a clear error (instead of wrong data) for an unknown ticket, SKU, size, lease, invoice, vendor, or account.

## Setup

```powershell
cd mcp_server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # same list as ../requirements.txt
```

## Running

```powershell
python mcp_server.py          # stdio, for a vibe-coder MCP config
python mcp_server.py --http   # Streamable HTTP at http://127.0.0.1:8001/mcp
```

For a vibe coder, point the MCP config at this folder's `.venv` Python and `mcp_server.py` (use full paths on your machine).

The agent team in `../backend` starts this server itself over stdio (one process shared by all five agents), so you do not need to run it separately for the dry run. It is also registered as `campus-customs` in the project's `.mcp.json` (portable: `python mcp_server/mcp_server.py`, run from the project root with this venv active).
