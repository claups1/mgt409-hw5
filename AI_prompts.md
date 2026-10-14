# AI Prompts Log

## Prompt 1

Today we will be working in folder HW 5. Create AI_prompts.md at the start of the assignment and keep it updated as you work . This file is the log of what I typed to you

## Problem 1: Vibe coder prompts

`We are going to start working in problem 1. Create one section for each problem 1-11 with the following names within the md file we have already created. This are the names: Problem 1: Vibe coder prompts Problem 2: Study the Campus Customs database, Problem 3: Build the MCP Server, Problem 4: Add the MCP Server to vibe coder and test each tool, Problem 5: Build the agent team and grow the MCP tools, Problem 6: Plan the three tickets, Problem 7: Backend routes Problem 8: Agent dashboard, Problem 9: Resolve the tickets, Problem 10: Reflection, Problem 11: Submit to Github`

`As we go trough each problem, please record my actual prompts in my own wording in corresponding section. If a follow up prompt is needed, add a sentence explaining what is missing. I’ll tell you which problem we are working once we begin`

## Problem 2: Study the Campus Customs database

`we are going to start working in problem 2 (please remember we are in HW 4).`

`Inspect every table and field in data/campus_customs.db, then copy it to data/campus_customs_new.db without modifying the original. Study the three open tickets and identify how they relate to other tables. Start output/harness.md with every table’s name, fields, and one short sentence explaining why it matters for the agents. Verify the database copy and confirm all tables and fields are documented.`

## Problem 3: Build the MCP Server

`we are going to start working in problem 3 (please remember we are in HW 5).`

`Build an MCP server in mcp_server/ using FastMCP, connected to data/campus_customs_new.db. Do not connect to or run the server yet.`

`Create exactly three  MCP tools based on the database and open tickets:`

`* Ticket 101: Help resolve the white T-shirt order, including checking size-S inventory and relevant pricing or reprint details.`

`* Ticket 102: Help evaluate the rent notice using lease, cash-account, and payment information.`

`* Ticket 103: Help evaluate the bulk order for 20 navy medium hoodies, including stock, pricing, and vendor information.`

`Use only verified database information; dont invent data. Each tool should query the relevant tables and return useful results for its ticket.`

`Update output/harness.md to document each tool's name, the table(s) it reads, the ticket it helps unlock (101, 102, or 103), and one specific sentence explaining why it is appropriate for that ticket.`

`Create mcp_server/README.md explaining the server's purpose, database file it uses, and all three tools.`

## Problem 4: Add the MCP Server to vibe coder and test each tool

`we are going to start working in problem 4 (please remember we are in HW 5).`

`Connect my MCP server to Claude Code and test each tool. The server is HW 5/mcp_server/mcp_server.py  with three tools: review_customer_order (ticket 101), review_rent_notice (ticket 102), and review_bulk_order (ticket 103).`

`Add the server to this project by saving the connection JSON in .mcp.json at the project root, and confirm it's connected with /mcp. If I need to restart or approve it first, tell me and stop; don't fake any tool calls.`

`Once connected, call each tool through the MCP connection using a simple prompt like "What's going on with ticket 101?". Save the results in output/mcp_smoke.json as a list of three objects with "prompt", "tool_name", and "tool_output" (the raw output, copied exactly). Check every number in the outputs against data/campus_customs_new.db with read-only queries, tell me if anything doesn't match, and don't modify the database`

Follow-up: the server first had to be restarted and approved before its tools were available, so the tool calls, smoke file, and number checks were not done yet; this prompt asked for them again once campus-customs was connected.

`We are going to continue Problem 4 (hw 5). campus-customs is connected. Call each of the three tools through the MCP connection, using a simple natural-language prompt for each (for example, "What's going on with ticket 101?"). Save the raw outputs to output/mcp_smoke.json as a list of three objects with "prompt", "tool_name", and "tool_output" (copied exactly, not summarized). Then verify every number against data/campus_customs_new.db with read-only queries, tell me if anything doesn't match, and don't modify the database.`

## Problem 5: Build the agent team and grow the MCP tools

`we are going to start working in problem 5 (please remember we are in HW 5).`

`We are going to build the Campus Customs agent team with PydanticAI and grow the MCP tools. Create five agents (Boss, Inventory, Accounting, Facilities, Customer Service) under backend/, with data types in backend/models.py and one prompt file per agent in backend/prompts/. Every agent uses only the model gpt-6-luna through Portkey, with the key read from the PORTKEY_API_KEY environment variable.`

`Write each prompt detailed: the agent's role and scope, the shop rules it needs, what it must not do, when to delegate to another agent, and how to format its answer. Give every agent a delegation tool for each of the other four so they are fully connected, with agent loops and sensible limits (max delegation depth, max steps and request limits, no infinite hand-offs).`

`Add whatever new tools the agents need to mcp_server/mcp_server.py so they can work tickets 101, 102 and 103. All shop facts must come from the MCP server over data/campus_customs_new.db, with no second shop-tools layer that bypasses MCP. Keep the tools read-only or propose-only, and never invent data.`

`Make the agents append one record per agent-loop step to output/audit_trail.json (agent, timestamp, ticket, step type, tool or delegation called, inputs, outputs), appending to the file rather than wiping it each run. In output/harness.md, list each agent and each MCP tool (including the new ones) with the table each tool uses, and add a short safety section covering guardrails for real customers and real money (human approval before payments or refunds, spending limits, no changes to the data without sign-off, privacy) plus token limits (max steps, max delegation depth, output length caps). Update mcp_server/README.md so the tool list matches the current server. Test with a dry run on the open tickets, confirm the audit trail grows across runs, check that the database is unchanged.`

Follow-up: the offline guardrail tests (loop guard, depth limit, hand-off budget, step cap) had only been run from a scratch folder, so they weren't saved in the project as evidence; this answer asked to copy them into backend/.

`yes`

## Problem 6: Plan the three tickets

`we are going to start working in problem 6 (please remember we are in HW 5).`

`We are going to build output/desk_tickets.html, a single self-contained that opens with a double-click. Add tabs for Ticket 101, Ticket 102, Ticket 103, Cash, and Reflection, with clean, readable styling. Cash and Reflection just say "Coming later".`

`Each ticket tab gets an "Expected" section that you fill in now, plus an empty "Actual" section with a note saying I'll fill it in after the agents run. Write Expected using only the ticket text, the database, and the tool list in mcp_server/mcp_server.py. Please don't look at audit_trail.json or the dry-run results, because this is supposed to be my prediction from before the run.`

`In each Expected section, say in plain words which agent the Boss should call first and why, every delegation I expect in order, which specialists are not needed and why (not "Boss calls everyone"), and the exact MCP tool names expected to run, taken from the real tool list. My hypothesis is the following: 101 goes Inventory, then Accounting (overdue invoice), then Customer Service, no Facilities; 102 goes Accounting (cash), then Facilities (lease), no Inventory or Customer Service; 103 goes Inventory, then Accounting (discount floor), then Customer Service, no Facilities. Check these against the ticket and database and adjust if they don't fit. Don't invent tool names or numbers.`

## Problem 7: Backend routes

`we are going to start working in problem 7 (please remember we are in HW 5).`

`In backend/main.py, use FastAPI to add the routes for the following:`

`1. Return the three tickets and show whether each one is open or resolved.`
`2. Take a ticket ID and run my existing agent team on that ticket.`
`3. Return recent agent events, including what each agent said and which tools it used, so the frontend can update.`
`4. Add a route to approve a payment or purchase. The agents should only prepare the payment, and money should only move after a human approves it.`
`5. Return the current checking balance from the cash_accounts table.`
`6. Add a route to reset the database to its original values so I can test everything again.`

`A few things to keep in mind:`

`* Use my existing database, agents, and tools. Don't rebuild things that are already implemented.`
`* Make sure payments can't happen automatically or be approved twice.`
`* Make sure the reset restores the original data correctly.`

`Then update output/harness.md with one line for each route, explaining the URL, HTTP method, and what it does.`
`To run the backend, the command should work from the backend/ folder:`
`uvicorn main:app --reload --port 8000`
`Don't claim anything works unless you've actually tested it.`

## Problem 8: Agent dashboard

`we are going to start working in problem 8 (please remember we are in HW 5).`

`We are going to look at my existing backend and Problem 7 routes before making changes.`
`Build the agent dashboard in frontend/ using React, Vite, and TypeScript.`
`The dashboard should:`

`* Show all three tickets`
`* Let me select a ticket and run the agent team.`
`* Show each agent and what they are saying / doing while the ticket runs`
`* Mark a ticket resolved when the run finishes`
`* Show a summary of what each agent did on that ticket`
`* Let me approve pending payments or purchases when asked`
`* Show the checking balance and update it after payments (it should drop after an approved pay)`

`Make the design look professional and creative, like a real operations dashboard. Use a clean layout with tickets, agent activity, approvals, and balance easy to see. Use a bit of glassmorphism for the shapes.`
`Connect the frontend to http://localhost:8000 and configure CORS for the Vite frontend. Use my existing routes and database, and don't use fake data.`
`Write output/design.md explaining the design choices(layout, how agents read differently,how resolved tickets and cash glow up) and why, including the creative choices that make it feel special and something humans would enjoy using. Then run the app with npm run dev, test the main features, fix any errors, and tell me what works and what files you changed.`

## Problem 9: Resolve the tickets

`we are going to start working in problem 9 (please remember we are in HW 5).`

`I want to resolve all three tickets on the live board and record the results. First, reset the working database (POST /reset) and tell me the starting checking balance. Then run tickets 101, 102, and 103 through the backend with real agent runs until each one is resolved, and append every run to output/audit_trail.json without wiping it. The agents only prepare payments, so when approvals are pending, stop and tell me exactly which ones to click in the board (amount, payee, and ticket) and wait for me. Don't approve anything yourself unless I say "approve for me," and never edit the database directly.`

`Once the tickets are resolved, open output/desk_tickets.html and fill in the Actual section on each ticket tab from this run: which agents worked, what they delegated, and which tools they used. Please don't touch my Expected text, because I want to compare the two. On the Cash tab, itemize the starting balance, how cash changed when each ticket resolved and why (which payment or purchase, and the dollar amount), and the ending balance. Work out every figure from the database, show the arithmetic, and make sure the ending balance matches cash_accounts exactly.`

`Also save output/resolved_tickets.json with, for each ticket, the id, final status, a short outcome, what each agent contributed, and any human approvals (who, when, and how much). Then save output/resolved_board.html, a page I can double-click that has a real screenshot of the React board for each resolved ticket (101, 102, and 103), with the images embedded so it works as a single file. Finish output/harness.md so it covers the tables, MCP tools, the five agents, API routes, the dashboard, and the safety rules, and only update design.md and mcp_server/README.md if something changed.`

Follow-up: after the three runs, the payments the agents prepared needed a human to approve them on the board (Claude was not allowed to approve), so this message confirmed I had clicked AP-0037 ($2,400 rent) and AP-0038 ($264 restock).

`done`

## Problem 10: Reflection

`we are going to start working in problem 10 (please remember we are in HW 5).`

`We are going to fill in the Reflection tab in output/desk_tickets.html. Use the answers below as the base, expand each one and back every point with real evidence from the ticket tabs, the Cash tab, output/resolved_tickets.json, and the tool list in mcp_server/mcp_server.py. Only use real numbers, tool names, and events, don't change the Expected, Actual, or Cash tabs, and put each of the five questions under its own heading.`

`1. Evaluating the agents: I'd judge them on whether the outcome was right, whether the cash math held up, and whether the guardrails worked. 101 was good because it offered sizes M, L, or XL and held the $840 invoice. 102 was clean and paid the $2,400 rent only after my approval. 103 was good because it caught the 12-hoodie shortfall and kept the discount at or above the $22 cost. Cash went from $3,400 to $736 and matched the database.`

`2. Actual vs Expected: 101 matched my plan (Inventory, then Accounting, then Customer Service, no Facilities). On 102 I expected Accounting first, then Facilities, but the Boss asked both at the same time. 103 matched my plan.`

`3. Simpler as one agent: 102 would be simpler as one agent with tools, because it was just rent, lease, and cash lookups with no real back-and-forth. The team is still better for 101 and 103, where inventory, money, and customer wording needed separate checks and different tool access.`

`4. Three problems the team could solve now: A customer asks if the white tee comes in size L and what it costs, with no order yet. Inventory checks stock and price, and Customer Service replies with propose_customer_reply. It's a quote, not a stock-out like 101. Rent and a new vendor invoice land in the same week, and checking can't cover both and keep the $500 reserve. Accounting checks cash and invoices, and propose_payment shows which to pay first. The shop needs hoodies fast for a campus event, so which vendor is quickest? Inventory compares vendor lead times, and propose_restock estimates cost and arrival, like the 12-hoodie restock on 103.`

`5. Three problems it couldn't solve: customer refunds or returns (needs a refund tool, an order-history table, and a payment-processor connection, plus a Customer Service/Accounting flow); demand forecasting for what to restock (needs a sales-history table, a forecast tool, and an Analyst agent); and dealing with a new vendor or price change (needs a vendor-comparison tool, a contract table, and a Procurement agent).`

## Problem 11: Submit to Github

`we are going to start working in problem 11 (please remember we are in HW 5).`

`We are going to get my project ready and push it to a public GitHub repo. First make the project match the expected layout (picture attached): AI_prompts.md, requirements.txt, .env.example, .gitignore, .mcp.json, and README.md at the root; data/ with both campus_customs.db and campus_customs_new.db; mcp_server/ with the server file and its README.md; frontend/; backend/ with main.py, models.py, and prompts/ (boss, inventory, accounting, facilities, customer_service); and output/ with harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json, resolved_board.html, audit_trail.json, and github_url.txt. Tell me about anything missing or named differently. My server file is mcp_server.py but the layout says server.py, so keep my name unless a rename is safe, and if you rename it, update .mcp.json, the backend, and every README so nothing breaks.`

`Don't push my real .env or any API key. Make sure .gitignore covers .env, the venvs (mcp_server/.venv and backend/.venv), node_modules, __pycache__, and build folders, and make .env.example list PORTKEY_API_KEY with a placeholder value. Search every file that will be committed, including audit_trail.json, for anything that looks like a key, and check that .mcp.json has no secrets and no paths that only work on my computer. Include both database files in the repo even if .gitignore would normally skip .db files. Make sure requirements.txt covers the Python packages the backend and MCP server need.`

`Write the README so someone can run it: copy the original database over the working copy for a clean run, start the MCP server, start the FastAPI backend (uvicorn main:app --reload --port 8000 from backend/), start the React board, and reset the database before a full three-ticket run. Include how to set PORTKEY_API_KEY, and the exact commands. Then create the public repo and push, save the repo URL in output/github_url.txt, and push that file too.`
