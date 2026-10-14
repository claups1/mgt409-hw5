# Campus Customs Agent Ops Desk: Design Notes

The dashboard (`frontend/`, React + Vite + TypeScript) is where a manager watches the agent team work a ticket and then approves the money. Every number on screen comes from the Problem 7 backend (`http://localhost:8000`). There is no placeholder or demo data.

## The idea: a calm, professional operations desk

Most of the time a manager has two questions: what needs me right now, and how much money do we have. The design answers both without searching. It looks like a quiet business tool at night: a deep navy room, slate panels, one blue accent for actions, and a soft champagne-gold glow that follows your attention. Colour is used only for meaning, so when something lights up it is because something happened or because you pointed at it.

## Layout

```
┌──────────────── header: brand · shop day · backend status · live run · Reset data ────────────────┐
│ Tickets          │ Agent activity (selected ticket)                              │ Checking balance │
│  #101  Open      │   ┌──── agent constellation (who is working, who asked who) ┐ │  $3,400.00       │
│  #102  Resolved  │   └──────────────────────────────────────────────────────────┘ │  sparkline       │
│  #103  Open      │   [Activity / Live]  [Summary]                                 │ Approvals (count)│
│  [Run agent team]│   feed of agent steps … / Boss's plan + one card per agent     │  name · role     │
│                  │                                                                │  pending cards   │
└──────────────────┴────────────────────────────────────────────────────────────────┴──────────────────┘
```

- **Left, the work queue.** The three tickets are on the left because that is where you start: pick one, press Run. The Run button only appears on the selected ticket, so it is always clear which ticket you are about to start. It is disabled for resolved tickets and while another run is going, because the backend allows one run at a time.
- **Centre, the story.** The widest column holds what is happening. The agent constellation on top gives the at-a-glance picture, and the feed or summary below gives the detail. Tabs keep the column calm: **Activity** (shown as **Live** while agents work), then it switches to **Summary** by itself when the run ends.
- **Right, money.** Balance and approvals sit together because they are one decision: you look at the cash, then decide whether to pay. The Approvals heading carries a blue count badge, so pending money is visible at a glance.
- **Header, context.** It shows the shop's own date (from the database, 2026-08-31, not the computer's clock), a gold dot when the backend is connected, a blinking blue "Live run" pill during a run, and **Reset data** for testing.
- **Responsive.** Below 1,250px the money panels move under the main pair, and below 820px everything stacks into one column.

## Colour and surfaces

| Role | Colour | Where it appears |
|---|---|---|
| Page | Dark navy gradient: `#0b1220` (top-left) → `#101a2c` → `#16233a` blue-slate (bottom-right), fixed while scrolling | The whole background, with a very faint champagne tint (7% opacity) in the top-right corner |
| Header | A slightly lighter version of the same gradient (`#15203a` → `#1b2943`) with a thin `#2c3a55` border | The top bar, so it stands apart from the page |
| Panels | Slate `#161a21` at 92% opacity with a light 8px blur, thin `#2a313d` border, soft shadow | Every card. It's a light touch of glass: the navy shows through faintly, but text sits on a solid-enough surface |
| Accent (action) | Blue `#3b6fd8` | Primary buttons (Run agent team, Approve & pay), the logo, the approvals count, the Boss's plan rule, lit hand-off lines, "payment" labels, the live-run pill, the balance sparkline |
| Attention | Champagne gold `#c9a96e`, used as low-opacity glows and thin borders (gold text `#d9be8c`) | Whatever you click, the selected ticket, the running pulse, button hover, the connected dot, approved payments, success toasts |
| Resolved | Green `#3fb984` | **Only** resolved tickets: the green border, the "Resolved" pill, the "✓ RESOLVED" badge, and the brief green flash when a ticket gets resolved |
| Waiting / caution | Amber `#d9a441` | "Open" and "Needs more info" pills, "Needs owner" tags, warnings |
| Money out / problems | Red `#e5636f` | The "−$" chip and red border when a payment lands, "below reserve" amounts, "Blocked", backend offline |

**Readability.** Text colours were measured on the panels: main text is 14.6:1, secondary text 7.6:1, and the faintest captions 5.0:1. Gold text is 8:1 or better, and header text is 12–13.5:1. All are above the WCAG AA 4.5:1 guideline. Gold appears only as borders, outside glows, and that one readable text tone, so it never sits behind words.

## How the agents read differently

Five agents talking at once could easily become a wall of text. Each agent has its own identity, so you can tell who is speaking without reading a name:

| Agent | Colour | Icon | Voice (how its words look) |
|---|---|---|---|
| Boss | indigo `#8b9cf7` | crown | **Memo:** slightly larger text with more line spacing, like a note from a manager. The final plan has a blue rule down its left side |
| Inventory | teal `#3fb8a9` | box | **Field notes:** plain and practical |
| Accounting | amber `#d6a54a` | ledger | **Ledger:** tabular numbers with a thin amber rule, like a bookkeeper's column |
| Facilities | violet `#a58bdf` | storefront | **Notice:** plain, factual text. Its violet badge and colour rail identify it |
| Customer Service | sky blue `#5aa6e0` | chat bubble | **Chat:** a speech bubble, because its words are for a customer |

All agents use the same font family, so the page stays consistent. The difference comes from colour, icon, size, and shape, not from mixing typefaces.

- **Indentation shows delegation.** A specialist's lines are indented by how deep in the chain it is, with a "via Boss" tag. You can see who asked whom without a diagram.
- **Tools look like tools.** MCP tool calls (`get_lease`, `propose_payment`, …) are small monospace chips. Hovering a chip shows the exact arguments, so "doing" (chips) is easy to tell apart from "saying" (sentences).
- **Hand-offs are quoted.** "→ Accounting 'please provide propose_payment for $2,400…'" shows the actual question one agent asked another.
- **Plumbing is hidden.** Internal "model request" steps aren't shown, and tool results collapse to one dim "✓ Got results" line. The feed is a story, not a log dump. The full log is still in `output/audit_trail.json`.

### The constellation

The five agents sit as round nodes, with the Boss on top and the specialists on an arc below. A faint dashed slate line joins every pair, because any agent *can* hand off to any other. A line turns solid blue the moment one agent actually hands work to another. Each node also shows its state:

- **Idle:** the icon is dimmed, but its label stays fully readable.
- **Thinking:** a gentle breathing ring in the agent's colour.
- **Using tools or delegating:** a solid ring in the agent's colour with a faint gold halo.
- **Done:** filled with a light tint of its colour.
- **Stopped:** a red ring.

After a run, the picture itself tells you how the work was divided. For example, on ticket 102 the Boss, Facilities, and Accounting light up while Inventory and Customer Service stay dim. That matches the prediction in `desk_tickets.html`.

## How attention, running, resolved tickets, and cash light up

- **Whatever you click glows gold.** Click a ticket, a panel (tickets, activity, balance, approvals, header), or an agent in the constellation, and it gets a thin champagne border and a soft gold glow. A clicked agent's ring and label turn gold. The glow moves with you: when you click somewhere else, it leaves. This includes the **Balance** and **Approvals** cards, which glow a little brighter while you're working in them and return to plain slate when you click away.
- **The selected ticket** keeps a gold border, a gold bar on its left edge, and a soft halo, so you always know which ticket the centre column is about.
- **While a run is going,** the running ticket and every agent that is thinking or working pulse slowly in brighter gold (about every 2.6 seconds). The pulse stops the moment the run, or that agent, finishes, so the page goes calm again when the work is done.
- **A ticket getting resolved** flashes green once, settles into a lasting green border, and shows a toast ("Ticket #103 resolved. The team finished its work."). Resolved tickets keep a green "Resolved" pill. When a resolved ticket isn't selected, it also shows a small "✓ RESOLVED" badge under its text, never on top of it. Green is reserved for this one meaning. If you select a resolved ticket, it keeps its green border and gets the gold glow around it.
- **Cash leaving the account.** The big number counts down to its new value instead of jumping, the card's border turns red, and a red "−$2,400.00" chip appears in the corner for a few seconds. You *see* the money leave, which is the honest feeling for a payment. A small blue sparkline under the number keeps this session's balance history.
- **Cash coming back** (after a reset) counts up with a gold border and a gold "+$" chip.
- **The animation has a safety net.** Even if the browser pauses animations (for example in a background tab), the card always lands on the exact balance the backend returned.
- **Calmer for some people.** If the computer is set to reduce motion, the pulses and breathing stop, and the brighter glow simply stays still.

## Approvals that feel safe

- Each pending card leads with **the amount** in large type, then who gets paid, why (rent due date, invoice number, or the restock quantity and arrival date), and the cash left afterwards. If paying would leave less than the reserve once the other known bills are paid, the card says "(below reserve)" in red. That flag comes from `propose_payment`'s own check, not the frontend.
- A coloured left edge shows which agent prepared it. An amber **"Needs owner"** or neutral **"Needs staff"** tag shows who has to sign off.
- You enter **your name and role** once (the browser remembers them). The blue button says exactly what will happen: "Approve & pay $264.00". It gets a gold glow on hover.
- If the backend refuses (for example, staff approving $2,400), its reason appears right on the card: "Owner approval required: amount is over the $500 staff limit." The dashboard never pretends a payment happened. The balance only changes after the backend confirms.
- Approved payments collect in a small **Approved** list in gold text at the bottom of the card.

## Small things that make it pleasant

- **One consistent system:** two corner sizes (14px for panels, 10px for inner cards), one border style, panel headers with a thin divider, and matching buttons, pills, and tabs.
- **A typing indicator** (three blue dots, "agents working") during a run, so long pauses don't feel broken.
- **The shop's date in the header,** so due dates ("due in 2 days") always make sense.
- **Friendly empty states:** "Nothing waiting. Payments and purchases the agents prepare appear here."
- **Keyboard and screen-reader basics:** tickets work with Enter and Space, blue focus rings for keyboard users, and live regions for the balance and toasts. Panels and agents can be clicked to focus them (for the gold glow) without adding extra stops to the keyboard Tab order.

## Why these choices

The course is about managers working *with* AI agents, so the dashboard has to build trust. You can watch what each agent did and with which tool, see the plan before anything happens, and stay in control of every dollar.

A calm navy-and-slate palette reads as a serious business tool rather than a toy. The gold glow gives it warmth and a sense of quality: it follows your clicks and pulses only while work is happening, so the screen feels alive when it should and quiet when it shouldn't. Distinct agent identities make the team feel like colleagues you can follow. Giving each colour a single job (blue to act, gold for attention, green for done, amber for waiting, red for money out) means you learn the meaning once and can then read the whole screen at a glance.
