# Campus Customs: AI Agent Team (MGT 409, HW 5)

A small campus apparel shop run by a team of five AI agents (Boss, Inventory, Accounting, Facilities, Customer Service). The agents read the shop's SQLite database **only through an MCP server**, prepare payments and purchases, and wait for a **human to approve** before any money moves. A FastAPI backend runs the team, and a React board shows the agents working live.

- **MCP server:** `mcp_server/mcp_server.py` (FastMCP, 18 read-only or propose-only tools)
- **Agents and API:** `backend/` (PydanticAI agents, FastAPI routes)
- **Board:** `frontend/` (React + Vite + TypeScript)
- **Model:** `gpt-6-luna` through Portkey (key in `PORTKEY_API_KEY`)
- **Results:** `output/` (harness, design notes, audit trail, resolved tickets, screenshots)

## Project layout

```
HW 5/
├── AI_prompts.md            # log of the prompts used to build this
├── requirements.txt         # Python packages for the MCP server and the backend
├── .env.example             # copy to .env and add PORTKEY_API_KEY
├── .gitignore
├── .mcp.json                # registers the MCP server for an MCP client (e.g. Claude Code)
├── README.md
├── data/
│   ├── campus_customs.db        # original database (never written)
│   └── campus_customs_new.db    # working copy (agents read it; approvals/reset write it)
├── mcp_server/
│   ├── mcp_server.py        # the MCP server ("server.py" in the assignment layout)
│   └── README.md
├── frontend/                # React board (npm run dev → http://localhost:5173)
├── backend/
│   ├── main.py              # FastAPI routes
│   ├── models.py            # data types
│   ├── agents.py, config.py, mcp_link.py, audit.py, approvals.py, ledger.py
│   ├── run_tickets.py       # command-line dry run
│   ├── test_guardrails.py   # offline guardrail tests (no API calls)
│   └── prompts/             # boss.md, inventory.md, accounting.md, facilities.md, customer_service.md
└── output/
    ├── harness.md, design.md, mcp_smoke.json, desk_tickets.html
    ├── resolved_tickets.json, resolved_board.html, audit_trail.json, approvals.json
    └── github_url.txt
```

## What you need

- **Python 3.12 or newer** (tested with 3.14)
- **Node.js 20 or newer** (tested with 24) and npm
- A **Portkey API key** that can call `gpt-6-luna`

The commands below are for **Windows PowerShell**, with macOS/Linux versions where they differ. Run them from the project folder (the folder that contains this README) unless a step says `cd`.

## 1. Set your API key

Copy the template, then open `.env` and replace the placeholder with your real key:

```powershell
Copy-Item .env.example .env
```

```bash
cp .env.example .env
```

`.env` should contain one line, `PORTKEY_API_KEY=<your key>`. The backend loads it automatically. `.env` is in `.gitignore`, so it is never committed.

(Alternative: set the key only for the current terminal, with `$env:PORTKEY_API_KEY = "<your key>"` in PowerShell or `export PORTKEY_API_KEY=<your key>` on macOS/Linux.)

## 2. Install the Python packages

Each Python part has its own virtual environment, and both use the root `requirements.txt`.

**MCP server**

```powershell
cd mcp_server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ..\requirements.txt
deactivate
cd ..
```

**Backend**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r ..\requirements.txt
deactivate
cd ..
```

On macOS/Linux, use `python3 -m venv .venv`, `source .venv/bin/activate`, and `pip install -r ../requirements.txt`.

## 3. Start from a clean database

Copy the original database over the working copy, so the run starts from the shop's original data (checking $3,400.00, three open tickets, no payments):

```powershell
Copy-Item data\campus_customs.db data\campus_customs_new.db -Force
```

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

## 4. Start the MCP server

The backend starts its **own** copy of the MCP server automatically (over stdio, using `mcp_server/.venv`), so this step is only needed to check or explore the tools on their own. In a terminal:

```powershell
cd mcp_server
.\.venv\Scripts\Activate.ps1
python mcp_server.py --http
```

This serves the 18 tools at `http://127.0.0.1:8001/mcp`. Run `python mcp_server.py` without `--http` for stdio, which is what MCP clients use. The project's `.mcp.json` registers the same server for an MCP client such as Claude Code. Start that client from this folder, with the MCP server's venv active, so `python` can find `fastmcp`.

## 5. Start the FastAPI backend

In a new terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

On macOS/Linux, activate with `source .venv/bin/activate`. The API runs at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

| Route | What it does |
|---|---|
| `GET /tickets` | All tickets, open or resolved |
| `POST /tickets/{id}/run` | Runs the agent team on one open ticket (`?wait=true` to wait) |
| `GET /events` | Agent steps from the audit trail (who acted, what they said, which tools) |
| `GET /approvals` | Payments and purchases the agents prepared |
| `POST /approvals/{id}/approve` | A human approves one; only then does money move |
| `GET /cash/checking` | Current checking balance |
| `POST /reset` | Copies the original database over the working copy and verifies it |

## 6. Start the React board

In a third terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The board talks to the backend at `http://localhost:8000`, and the backend allows local Vite ports through CORS.

## 7. Full three-ticket run

1. **Reset the database first**, with the board's **Reset data** button, or:

   ```powershell
   Invoke-RestMethod -Method Post http://localhost:8000/reset
   ```

   ```bash
   curl -X POST http://localhost:8000/reset
   ```

   The response should say `"matches_original": true`. Checking is back to $3,400.00.

2. **Run each ticket.** On the board, select ticket 101 and press **Run agent team**, then do the same for 102 and 103. Or use the API:

   ```powershell
   foreach ($t in 101, 102, 103) { Invoke-RestMethod -Method Post "http://localhost:8000/tickets/$t/run?wait=true" }
   ```

   ```bash
   for t in 101 102 103; do curl -X POST "http://localhost:8000/tickets/$t/run?wait=true"; done
   ```

   Each run is appended to `output/audit_trail.json`, and each ticket is marked resolved when its run finishes.

3. **Approve payments as a human.** On the board, enter your name, pick **Staff** or **Owner**, and click **Approve & pay** on the items you want. Staff can approve up to $500. Larger amounts, or anything that would drop cash below the $500 reserve, need the owner. The checking balance updates after each approval.

## Tests and a command-line dry run

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python test_guardrails.py     # offline: loop guard, depth limit, hand-off budget, step cap (no API key needed)
python run_tickets.py         # real dry run of 101-103 in the terminal (uses your Portkey key)
```

## Safety rules (summary)

- Agents can only **read** data or **propose** actions. The MCP server opens the database read-only.
- Money moves only through `POST /approvals/{id}/approve`, after a human approves. Each approval works once, and payments can't be approved twice.
- Customer replies are drafts, checked for internal figures and other customers' names.
- There are limits on delegation depth, hand-offs, steps, requests, and tokens.

Full details are in `output/harness.md`. The board's design is described in `output/design.md`.
