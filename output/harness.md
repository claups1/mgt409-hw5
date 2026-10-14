# Harness — Campus Customs Agent Team

**Where to find each part**

| Topic | Section |
|---|---|
| Database tables, fields, links, and the three tickets | Problem 2 |
| MCP tools (18) and the tables each one reads | Problem 3, Problem 5 "MCP tools", Problem 7 (`list_tickets`) |
| The five agents, their tools, delegation, and the audit trail | Problem 5 |
| Safety rules (money, data, privacy, token and loop limits) | Problem 5 "Safety guardrails", Problem 7 "How payments stay safe", summary in Problem 9 |
| API routes | Problem 7 |
| Dashboard | Problem 8 (design details in `output/design.md`) |
| Resolving the three tickets, cash, and results | Problem 9 |

## Problem 2: Campus Customs database

**Source:** `data/campus_customs.db` (original, read-only — never modified)
**Working copy:** `data/campus_customs_new.db` (agents read it through MCP; only human-approved payments, run resolution, and reset write to it)

The copy was made with SQLite's built-in backup API while the original was opened in read-only mode, so the original file could not be changed. The original's SHA-256 hash was checked before and after copying and is unchanged.

The database has **9 tables**. The shop's "today" is **2026-08-31** (from `desk.date_today`).

### Tables, fields, and why they matter

| Table | Rows | Fields | Why it matters for the agents |
|---|---|---|---|
| `tickets` | 3 | `id` (PK), `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` (FK → leases), `invoice_id` (FK → invoices), `status`, `notes`, `created_at` | This is the agents' work queue: each open ticket is a request they must investigate and resolve. |
| `inventory` | 10 | `sku` (PK part), `name`, `size` (PK part), `qty`, `location` | Tells agents whether a requested product and size is actually in stock and where to find it. |
| `pricing` | 4 | `sku` (PK), `unit_cost`, `list_price` | Sets the price floor (cost) and normal price, so agents can judge any discount without selling at a loss. |
| `vendors` | 3 | `id` (PK), `name`, `specialty`, `lead_days` | Shows who can restock or deliver items and how many days it takes, which affects promises to customers. |
| `invoices` | 1 | `id` (PK), `vendor_id` (FK → vendors), `amount`, `due_date`, `status`, `description` | Lists bills the shop owes vendors, so agents know what is due or overdue before spending cash. |
| `leases` | 1 | `id` (PK), `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Records the shop's rent obligation, which is a fixed bill that must be paid on time. |
| `cash_accounts` | 1 | `name` (PK), `balance`, `date` | Shows how much money is available, so agents never approve payments the shop cannot afford. |
| `payments` | 0 | `id` (PK), `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | The audit log of money going out; `approved_by` is required, so every payment must name who approved it. |
| `desk` | 1 | `date_today`, `notes` | Gives agents the shop's official "today" date so due dates and deadlines are judged consistently. |

### How the tables connect

Formal foreign keys (declared in the schema):
- `tickets.invoice_id` → `invoices.id`
- `tickets.lease_id` → `leases.id`
- `invoices.vendor_id` → `vendors.id`

Informal links (matched by value, not enforced by the database):
- `tickets.sku` / `tickets.size` → `inventory.sku` / `inventory.size`
- `tickets.sku` → `pricing.sku`, and `inventory.sku` → `pricing.sku`
- `payments.account` → `cash_accounts.name`
- `payments.kind` + `payments.ref_id` → an `invoices.id` or `leases.id`, depending on the kind of payment

### The three open tickets

All three tickets are dated 2026-08-31 and have `status = 'open'`.

**Ticket 101: customer order (Tauhid Zaman, "Bulldog tee")**
- Asks for 1 × `CC-TEE-WHITE` (Classic Bulldog Tee), size **S**.
- **inventory:** size S has **qty 0**, so it is out of stock (M = 5, L = 3, XL = 2 are available).
- **pricing:** list price $28.00, unit cost $8.00.
- **invoices:** linked to invoice **501**, "Rush reprint CC-TEE-WHITE S" for **$840.00**. It was due **2026-08-28**, so it is **3 days overdue** and still open.
- **vendors:** invoice 501 is from vendor 1, **Bulldog Print Co** (apparel reprint, 5-day lead time).
- **Key tension:** a $28 sale is tied to an $840 overdue vendor bill, and restocking takes about 5 days.

**Ticket 102: rent notice (Elm City Properties, "Rent due")**
- **leases:** linked to lease **1**, Chapel Street shop, **$2,400.00/month**, next due **2026-09-02** (2 days from today).
- **cash_accounts:** checking balance is **$3,400.00**.
- **payments:** no payments have been recorded yet. Paying rent needs a `payments` row with `kind`, `ref_id = 1`, `account = 'checking'`, and an `approved_by` name.
- **Key tension:** rent ($2,400) plus invoice 501 ($840) comes to **$3,240**, which would leave only **$160** in checking. Payments need human approval.

**Ticket 103: price override (Yale AI Club, "Bulk hoodie discount")**
- Asks for 20 × `CC-HOOD-NAVY` (Basic Hoodie Big Yale), size **M**, at a bulk discount.
- **inventory:** size M has only **qty 8**, which is **12 short** (S = 4, L = 14, XL = 6).
- **pricing:** list price $58.00, unit cost $22.00. Twenty hoodies cost $1,160 at list price, and the shop breaks even at $440. Any discount must stay above cost.
- **vendors:** Bulldog Print Co (apparel) could restock in about 5 days.
- **Key tension:** this needs a pricing decision and a stock-shortage plan before anything is promised to the customer.

### Verification checklist

- [x] Original `campus_customs.db`: SHA-256 hash is the same before and after the copy, and `PRAGMA integrity_check` returns `ok`.
- [x] Copy `campus_customs_new.db`: same 9 tables, same columns, and same row counts as the original, with identical contents in every table.
- [x] All 9 tables and all 48 fields are documented above.

## Problem 3: MCP server tools

**Server:** `mcp_server/mcp_server.py` (FastMCP, server name `campus-customs`)
**Database:** `data/campus_customs_new.db`, opened **read-only** so these tools cannot change any data.

All three tools return only values read from the database, plus simple arithmetic on those values (totals, shortfall, days overdue or until due). Each tool checks that the ticket exists and is the expected type before answering.

| Tool | Tables it reads | Ticket it unlocks | Why it is appropriate for that ticket |
|---|---|---|---|
| `review_customer_order` | `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `desk` | **101** | It shows that the size-S white tee has 0 in stock, while the linked $840 reprint invoice from Bulldog Print Co is 3 days overdue with a 5-day lead time, which is exactly what the agent needs to decide whether to offer another size or wait for the reprint. |
| `review_rent_notice` | `tickets`, `leases`, `payments`, `cash_accounts`, `invoices`, `vendors`, `desk` | **102** | It confirms the $2,400 Chapel Street rent is due in 2 days, that no rent payment is recorded yet, and that paying it with the open $840 invoice would leave only $160 of the $3,400 in checking, so the agent can judge whether paying rent is safe before asking a human to approve it. |
| `review_bulk_order` | `tickets`, `inventory`, `pricing`, `vendors`, `desk` | **103** | It shows that only 8 of the 20 requested size-M hoodies are in stock (12 short) and that the $1,160 list total has a $440 cost floor, so the agent can propose a discount that never sells below cost and a restock plan based on real vendor lead times. |

## Problem 5: Agent team and expanded MCP tools

**Code:** `backend/` (PydanticAI). **Model:** every agent uses `gpt-6-luna` through Portkey, through the OpenAI Responses API. The key is read from the `PORTKEY_API_KEY` environment variable at runtime and is never printed or stored.
**Shop facts:** come only from the `campus-customs` MCP server (`mcp_server/mcp_server.py`, database opened read-only). The agents have no SQL and no other shop-data code. (Problem 7 later adds `backend/ledger.py`, which writes only after a human approves; agents can't reach it.) Each agent gets a filtered view of the same MCP connection, so it sees only the tools for its job (`backend/mcp_link.py`).

| File | What it holds |
|---|---|
| `backend/agents.py` | The five agents, the delegation tools, the agent loop, and the guardrails |
| `backend/models.py` | Data types: `Proposal`, `SpecialistReport`, `TicketDecision`, `AuditRecord` |
| `backend/prompts/*.md` | One detailed prompt per agent: role and scope, shop rules, must-nots, when to delegate, answer format |
| `backend/mcp_link.py` | MCP connection (stdio) and each agent's tool allowlist |
| `backend/audit.py` | Append-only audit trail writer |
| `backend/config.py` | Model and Portkey setup, paths, and every numeric limit |
| `backend/run_tickets.py` | Dry run over the open tickets, with database-hash and audit-growth checks |

### Agents

Every agent has an `ask_<agent>` delegation tool for each of the other four, so the team is fully connected (20 delegation tools in total).

| Agent | Prompt | Role | MCP tools it can call | Answer type |
|---|---|---|---|---|
| **Boss** | `boss.md` | Receives each ticket, chooses specialists, checks their numbers against the ticket review, and writes the plan a human approves | `get_ticket`, `list_open_tickets`, `get_shop_policy`, `review_customer_order`, `review_rent_notice`, `review_bulk_order` | `TicketDecision` |
| **Inventory** | `inventory.md` | Stock by SKU and size, shortfalls, vendors and lead times, restock proposals (flags duplicate reprints) | `get_ticket`, `get_shop_policy`, `check_inventory`, `get_pricing`, `list_vendors`, `propose_restock` | `SpecialistReport` |
| **Accounting** | `accounting.md` | Cash, open invoices, payments, margins, and payment and discount proposals with approval level | `get_ticket`, `get_shop_policy`, `get_cash_position`, `get_invoice`, `get_lease`, `list_payments`, `get_pricing`, `propose_payment`, `propose_discount` | `SpecialistReport` |
| **Facilities** | `facilities.md` | The lease: rent, landlord, due date, already paid or not, and whether a notice matches the lease | `get_ticket`, `get_shop_policy`, `get_lease`, `list_payments` | `SpecialistReport` |
| **Customer Service** | `customer_service.md` | Customer reply drafts that offer only confirmed options and pass the privacy check | `get_ticket`, `get_shop_policy`, `check_inventory`, `propose_customer_reply` | `SpecialistReport` |

Customer Service has no access to costs, cash, invoices, or rent, and `check_inventory` returns only the public list price. Facilities can't see cash, so affordability questions have to go to Accounting.

### MCP tools (17 in Problem 5; `list_tickets` added in Problem 7)

| Tool | Kind | Tables it uses | Used by |
|---|---|---|---|
| `review_customer_order` | read-only | `tickets`, `inventory`, `pricing`, `invoices`, `vendors`, `desk` | Boss (101) |
| `review_rent_notice` | read-only | `tickets`, `leases`, `payments`, `cash_accounts`, `invoices`, `vendors`, `desk` | Boss (102) |
| `review_bulk_order` | read-only | `tickets`, `inventory`, `pricing`, `vendors`, `desk` | Boss (103) |
| `list_open_tickets` *(new)* | read-only | `tickets`, `desk` | Boss |
| `list_tickets` *(Problem 7)* | read-only | `tickets`, `desk` | Backend `GET /tickets` (no agent) |
| `get_ticket` *(new)* | read-only | `tickets`, `desk` | all five |
| `get_shop_policy` *(new)* | read-only | `desk` + `SHOP_POLICY` settings (policy, not a table) | all five |
| `check_inventory` *(new)* | read-only | `inventory`, `pricing` (list price only) | Inventory, Customer Service |
| `get_pricing` *(new)* | read-only | `pricing` | Inventory, Accounting |
| `list_vendors` *(new)* | read-only | `vendors` | Inventory |
| `get_cash_position` *(new)* | read-only | `cash_accounts`, `invoices`, `vendors`, `leases`, `payments`, `desk` | Accounting |
| `get_invoice` *(new)* | read-only | `invoices`, `vendors`, `payments`, `desk` | Accounting |
| `get_lease` *(new)* | read-only | `leases`, `payments`, `desk` | Accounting, Facilities |
| `list_payments` *(new)* | read-only | `payments` | Accounting, Facilities |
| `propose_payment` *(new)* | propose-only | `leases` or `invoices`, `vendors`, `payments`, `cash_accounts`, `desk` | Accounting (102, and invoice 501) |
| `propose_discount` *(new)* | propose-only | `pricing`, `inventory`, `desk` | Accounting (103) |
| `propose_restock` *(new)* | propose-only | `inventory`, `vendors`, `pricing`, `cash_accounts`, `invoices`, `desk` | Inventory (101, 103) |
| `propose_customer_reply` *(new)* | propose-only | `tickets`, `pricing`, `cash_accounts`, `invoices`, `leases` | Customer Service (101, 103) |

### Audit trail

`output/audit_trail.json` is a JSON list with **one record per agent-loop step**: the task arriving, each model request, each model response (with the tools or delegations it called and their inputs), each batch of tool results (outputs), the final output, and any guardrail stop or error. Each record has `run_id`, `timestamp`, `ticket_id`, `agent`, `depth`, `chain` (who delegated to whom), `step`, `step_type`, `called` (`mcp:<tool>` or `delegate:<agent>`), `inputs`, `outputs`, and `usage` (tokens). New records are **appended**. The file is rewritten atomically and never wiped, and if it isn't valid JSON the run stops rather than overwrite it.

### Safety guardrails

**Real customers and real money**
- **Human approval before payments or refunds.** No tool can pay, refund, order, discount, or send. The `propose_*` tools return a proposal with status `awaiting_human_approval` (or `blocked`), and the proposed payment row has `approved_by: null`. Every agent prompt forbids saying anything was paid, approved, or sent.
- **Spending limits** (`SHOP_POLICY`, policy chosen for this assignment). Agents can spend $0 on their own. Staff may approve up to **$500**, and anything above needs the **owner**. Plans that leave cash below a **$500 reserve** are flagged. Agents may propose up to a **15%** discount, and more needs the owner. Selling **below unit cost** is blocked outright. `propose_payment` also blocks payments the account can't cover, bills already paid, and closed invoices.
- **No changes to the data without sign-off.** The MCP server opens `campus_customs_new.db` in SQLite read-only mode, there are no write tools, and the agents never touch the database. Writing an approved action (a `payments` row with `approved_by`) is a separate, human-triggered step, added in Problem 7 as `POST /approvals/{id}/approve`.
- **Privacy.** Customer replies are drafts only. `propose_customer_reply` flags internal figures (unit costs, balances, invoice and rent amounts), internal-only words, other customers' names, and replies over **1,200 characters**. Customer Service can't reach financial tools. The API key comes from the environment and never appears in code, logs, or the audit trail. The audit trail holds customer names and internal figures, so treat it as internal and don't share it publicly.

**Token and loop limits** (all in `backend/config.py`)

| Limit | Value | What it stops |
|---|---|---|
| Max delegation depth | 2 | Boss → specialist → one more specialist, no deeper |
| Loop guard | no agent twice in a chain | A → B → A ping-pong (infinite hand-offs) |
| Max hand-offs per ticket | 6 | Too many delegations across the whole team |
| Max steps per agent run | 14 loop steps (about 6 model calls) | One agent looping on tools |
| Team limits per ticket (shared) | 30 model requests, 45 tool calls, 300,000 tokens | Runaway spend across all agents |
| Output cap per response | 2,500 tokens | Very long answers (includes reasoning tokens) |
| Answer length caps | `models.py` field limits (e.g. summary 900 chars, reply 1,200, max 10 facts) | Bloated answers. Over-long answers fail validation and the model must shorten them |
| Audit field cap | 4,000 characters | One tool result bloating the trail |

Blocked delegation tools are hidden from the model, and each tool re-checks the same rules in case it is called anyway. An offline stress test, using a fake model that delegates to everyone it can, confirmed the following: depth never went past 2, no agent repeated in a chain, hand-offs stopped at 6 (the extra parallel calls were blocked by the re-check), and an agent that never stops calling tools was halted at 14 steps with a `guardrail` record. Re-run it any time with `.venv\Scripts\python.exe test_guardrails.py` from `backend/` (14/14 checks pass). It makes no API calls and writes to a temporary audit file, not `output/audit_trail.json`.

### Dry run on the open tickets

Run from `backend/`: `.venv\Scripts\python.exe run_tickets.py` (tickets 101, 102, 103, with Boss as the entry agent). It was run 4 times. Every ticket finished `ok` in every full run, with no guardrail stops.

| Run | Tickets | Audit trail records | Database SHA-256 |
|---|---|---|---|
| 1 | 102 | 0 → 22 | unchanged |
| 2 | 101, 102, 103 | 22 → 116 | unchanged |
| 3 | 101, 102, 103 | 116 → 210 | unchanged |
| 4 | 101, 102, 103 | 210 → 306 | unchanged (`d6b8783e…`) |

What the team proposed in run 4 (all awaiting human approval, nothing executed):
- **101:** `needs_more_info`. Size S is out. The team offers M, L, or XL at $28 in a privacy-checked draft, and holds off on a new restock because the open, overdue $840 invoice 501 is already a rush reprint of this exact SKU and size. Paying 501 alongside rent would leave $160, below the reserve, so that is an owner decision.
- **102:** `ready_for_human_review`. The owner should approve the $2,400 rent from checking (due 2026-09-02, not yet paid), which leaves $1,000. The team flags that also paying invoice 501 would leave $160, $340 below the reserve.
- **103:** `ready_for_human_review`. Only 8 of 20 are in stock. Proposed: a restock of 12 from Bulldog Print Co (estimated $264, earliest 2026-09-05), a 15% discount ($49.30 each, $986 total, above cost, within agent authority), and a reply offering the 8 in stock without promising the rest.

Agent answers vary a little between runs because the model isn't deterministic. For example, ticket 103's discount was 10% in runs 2–3 and 15% in run 4, and ticket 101's status was `ready_for_human_review` in run 2 and `needs_more_info` in runs 3–4. The numbers behind each proposal always come from the `propose_*` tools.

## Problem 7: Backend routes

`backend/main.py` (FastAPI). Run it from `backend/` with the venv active: `uvicorn main:app --reload --port 8000` (docs at `http://127.0.0.1:8000/docs`).

- `GET /tickets`: lists all three tickets with their status and `is_open` / `is_resolved` flags (MCP `list_tickets`).
- `POST /tickets/{ticket_id}/run`: starts the existing agent team on one open ticket as a dry run and returns a `run_id` (202). Add `?wait=true` to wait for the result. Payments and purchases the agents prepare become pending approvals. When the run finishes successfully, the ticket is marked `resolved` (status only, no money; added in Problem 8). Returns 404 for an unknown ticket, and 409 if the ticket is resolved or a run is already going.
- `GET /events?since=&run_id=&ticket_id=&limit=`: recent agent-loop steps from `output/audit_trail.json`, with the agent, its chain, the step type, what it said, the MCP tools used, and any delegations. Also returns `next_since` for polling and the active run.
- `GET /approvals?status=`: lists the payments and purchases the agents prepared (`pending`, `approved`, `cancelled_by_reset`). Nothing has moved money unless the status is `approved`.
- `POST /approvals/{approval_id}/approve`: body `{"approved_by", "role": "staff"|"owner", "resolve_ticket"}`. A human approves one prepared payment or purchase, and only then does money move: a `payments` row is written, checking goes down, rent moves `next_due` one month or the invoice becomes `paid`, and the ticket is optionally resolved.
- `GET /cash/checking`: the current checking balance from `cash_accounts` (MCP `get_cash_position`).
- `POST /reset`: copies the original `data/campus_customs.db` over `data/campus_customs_new.db`, verifies the schema and every row against the original, and cancels pending approvals. Returns 409 while a run is going.

**How payments stay safe**
- Agents only prepare payments. Approvals are captured from the `propose_payment` / `propose_restock` tool output with status `awaiting_human_approval`, never from the model's own text.
- `backend/ledger.py` is the only code that writes to the database: approvals (money), reset, and marking a ticket resolved after a human-started run finishes (Problem 8). It isn't an agent or MCP tool.
- An approval works only once. The route refuses anything not `pending` (409). Inside one locked database transaction, the ledger also refuses an approval id already recorded in `payments.approved_by`, rent whose due date has moved on, and invoices that aren't `open`.
- The role is checked against `SHOP_POLICY`: staff may approve up to $500 when cash stays above the $500 reserve, and anything else needs the owner (403). The role is self-declared because this classroom demo has no logins; a real shop would need sign-in.
- A restock purchase pays the estimate at catalog unit cost and doesn't change stock (the goods arrive after the vendor's lead time).

**Tested** (live server on port 8000, real `gpt-6-luna` runs)
- `GET /tickets`, `/cash/checking`, `/events`, and `/approvals` returned the expected data. An unknown ticket returned 404.
- A run of 102 returned 202, and a second run or a reset while it was busy returned 409. Events streamed every step. The run left the database hash unchanged and created one pending approval (the $2,400 rent, owner).
- Approving as staff returned 403, and a blank name returned 422. Approving as owner wrote payment 1, took checking from $3,400 to $1,000, moved the lease to 2026-10-02, and resolved 102. A second approval returned 409, and running resolved 102 returned 409. Calling the ledger directly with the same approval, or with a new id for the same rent, was refused (409).
- Two simultaneous approvals of the 103 restock ($264, staff): one returned 200 and one 409, with one payment row and checking at $3,136. Hoodie stock stayed at 8.
- The 101 run produced an invoice-501 approval ($840, owner). Approving it marked the invoice `paid` (checking $2,560), and a second approval returned 409.
- `POST /reset` reported `matches_original: true`. An independent row-by-row comparison and `PRAGMA integrity_check` agreed. Checking was back to $3,400, all tickets open, a pending approval was cancelled (and can't be approved later), and the original database's hash was unchanged.

## Problem 8: Agent dashboard

`frontend/` (React + Vite + TypeScript). Run it with `npm run dev` from `frontend/` (http://localhost:5173), with the backend running on port 8000. Design notes are in `output/design.md`.

- It uses the Problem 7 routes only: `GET /tickets`, `POST /tickets/{id}/run`, `GET /events` (polled about once a second during a run), `GET /approvals`, `POST /approvals/{id}/approve`, `GET /cash/checking`, and `POST /reset`. There is no fake data.
- Backend changes for the dashboard:
  - CORS now allows only local Vite origins (`http://localhost:51xx` / `127.0.0.1:51xx`), with `GET` and `POST`.
  - A successful run marks its ticket resolved.
  - `GET /events` now includes each step's token `usage` for the per-agent summary.
- Tested in the browser:
  - Ticket 102 run live, then resolved, then an owner-only $2,400 approval appeared. Staff was refused with the backend's message; the owner approval took checking from $3,400 to $1,000.
  - Ticket 103 run live (four agents active, three hand-off lines lit), then the resolve glow and toast, then a $264 purchase approved by staff took checking from $1,000 to $736.
  - Reset brought checking back to $3,400 and all tickets open, and the database matched the original.
- Later visual refinements (styling only, no behaviour or data changes):
  - A professional navy and slate palette with a blue action colour.
  - A champagne-gold glow on whatever you click and a slow gold pulse while a run is going.
  - Green reserved for resolved tickets, and a clean "✓ RESOLVED" badge.
  - `tabIndex={-1}` on panels and agent nodes so a click can focus them.
  - All described in `output/design.md`.

## Problem 9: Resolving the three tickets

**Process.** `POST /reset` restored the working copy (verified identical to the original), with checking at **$3,400.00**. Tickets 101, 102, and 103 were run one at a time through `POST /tickets/{id}/run` with real `gpt-6-luna` agent runs. Each run finished `ok` and marked its ticket `resolved`, and every step was appended to `output/audit_trail.json` (1,064 → 1,160 records, nothing wiped). The agents prepared four approvals. A human (Claudia, owner) approved two on the board, and the other two were deliberately left pending on the Boss's advice. No database edits were made outside the backend's approval route.

| Ticket | Run | Boss decision | Agents (hand-offs sent together) | Money |
|---|---|---|---|---|
| 101 Bulldog tee | `20261013-234100-a90ec9` | needs more info | Boss → Inventory, Accounting, Customer Service | None. AP-0035 ($8 restock) and AP-0036 ($840 invoice 501) held |
| 102 Rent due | `20261013-234109-432a2d` | ready for human review | Boss → Facilities, Accounting | AP-0037 **$2,400.00** rent to Elm City Properties, approved by Claudia (owner) → payment #1 |
| 103 Bulk hoodie discount | `20261013-234117-f2aec3` | ready for human review | Boss → Inventory, Accounting, Customer Service | AP-0038 **$264.00** restock (12 × $22) from Bulldog Print Co, approved by Claudia (owner) → payment #2 |

**Cash.** $3,400.00 − $2,400.00 − $264.00 = **$736.00**, which equals `cash_accounts` checking (736.0) and `SUM(payments.amount)` = 2,664.00. Invoice 501 ($840, overdue) is still open, and $736 can't cover it.

**Outputs**
- `output/desk_tickets.html`: Actual sections for 101–103 and an itemized Cash tab. The Expected text is unchanged (verified with a hash before and after).
- `output/resolved_tickets.json`: for each ticket, the status, outcome, each agent's contribution and tools, and the human approvals (who, when, how much, payment row).
- `output/resolved_board.html`: a single file with real screenshots of the React board for 101, 102, and 103, with the images embedded.

**Guardrails seen working in this run**
- Output validation rejected the Boss's first plan on 101 because it cited `ask_inventory` as a source. The Boss corrected it.
- No step, depth, or usage limit was hit.
- Every payment waited for a human. AP-0037 ($2,400) required the owner because it was over the $500 staff limit. AP-0038 ($264) needed only staff, and Claudia approved it as owner.

### Safety rules at a glance
- **Money moves only after a human approves.** Agents can only call `propose_*` tools. The single write path is `POST /approvals/{id}/approve` (`backend/ledger.py`), which re-checks the bill, the balance, and the approver's role inside one locked transaction.
- **Spending limits** (`SHOP_POLICY`):
  - Staff can approve up to $500. Above that needs the owner.
  - A $500 cash reserve is enforced: falling below it needs the owner.
  - Discounts above 15% need the owner, and selling below unit cost is blocked.
- **No double payment.** Each approval is single-use. The approval ID is recorded on the payment row, the rent due date must still match, and the invoice must still be `open`.
- **No data changes without sign-off.** The MCP server opens the database read-only. Only approvals, run resolution (ticket status only), and `POST /reset` write to it, and the original `campus_customs.db` is never written.
- **Privacy.** Customer replies are drafts checked by `propose_customer_reply` for internal figures, internal words, other customers' names, and length. Customer Service can't see costs or cash. The API key comes from the environment only.
- **Token and loop limits:**
  - Hand-off depth 2, with no agent repeated in a chain.
  - 6 hand-offs per ticket and 14 steps per agent.
  - 30 requests, 45 tool calls, and 300k tokens per ticket.
  - 2,500 output tokens per response, plus field length caps.
