# PagerSage UI handoff

Design for the PagerSage frontend (task board area U, tasks U01–U09). Build it in `frontend/` (Next.js, from S03).

Design canvas (owner-only link): https://claude.ai/artifact/1zU7hYha5kUUaoqraxqnZi
The four screens are also in `design/` next to this file. Each `.dc.html` is a design-tool file, not runnable app code. Read it for structure, copy and the exact inline styles. Do not copy its `<script>` runtime or `support.js`.

## Prompt for Claude Code

> Read `docs/ui-handoff/HANDOFF.md` and the four files in `docs/ui-handoff/design/`. Implement the PagerSage frontend in `frontend/` to match them: the design tokens, the app shell, then the screens in the build order below. Code against the formats in `docs/contracts.md` and the endpoints listed per screen. Use stub data in the S02 formats wherever an endpoint isn't merged yet. Do not edit the task board or any task status. Show me the plan before writing code.

## Ground rules

- Do not change the PagerSage task board, task status or claims. Only Mahesh updates it.
- Names, times and scores in the designs are demo placeholders from the pool-exhaustion scenario. Real values come from the API.
- Amber marks only what PagerSage found: the root-cause path, Ask evidence, the "Cause" suspect and the primary button. Never use it for decoration.
- Blue marks agent activity: live indicators, blast radius, links and focus rings.
- Rollback is simulated (B09). The UI says so in one plain line.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--bg` | `#121628` | Page ground |
| `--bg-deep` | `#151A2E` | Graph canvas well |
| `--panel` | `#1A1F35` | Panels |
| `--raised` | `#232A45` | Selected rows, decision cards, chips |
| `--line` | `#2F375A` | Panel borders, dividers |
| `--line-soft` | `#262D4A` | Unselected row borders, bar tracks |
| `--line-strong` | `#4A5480` | Selected row border, input border (`#3B4570`) |
| `--text` | `#E9EBF4` | Primary text |
| `--text-2` | `#C9CEE0` | Secondary text |
| `--muted` | `#98A1BF` | Meta, captions (passes 4.5:1 on panel) |
| `--faint` | `#6B7497` | Formula lines, queued state only |
| `--amber` | `#FFB547` | Found / cause / primary action |
| `--amber-tint` | `#2C2718` | Amber chip and node background; text on it `#F4E6CC` |
| `--on-amber` | `#1A1406` | Text on amber buttons |
| `--blue` | `#79B4FF` | Agent activity, blast radius, links, focus |
| `--blue-tint` | `#1E2C47` | Pressed toggle background |
| `--danger` | `#FF7A7A` | Fragility ring |
| `--sev1-bg` / `--sev1-fg` | `#3A1F28` / `#FF9C9C` | Sev 1 pill, decoy pill |
| `--sev2-bg` / `--sev2-fg` | `#3A2F1C` / `#FFCB7A` | Sev 2 pill |
| `--ok` | `#6FD3B0` | Runbook success squares, live dot |
| `--ok-bg` / `--ok-fg` | `#1C3330` / `#8FE0C4` | Resolved pill, "Sent" / "Done" text |

Team colors (company graph only): Payments `#79B4FF`, Checkout `#C79BFF`, Platform `#6FD3B0`, Data `#F2A0C8`, no owner = dashed `#8A93B3` outline.

**Type.** Schibsted Grotesk 400/500/600/700 for everything. JetBrains Mono 400/500 only for ids, shas, tool calls, scores and timestamps. Both come from Google Fonts (use `next/font/google`).

| Role | Size / line height | Weight |
|---|---|---|
| Page title | 32 / 38, letter-spacing -0.02em | 600 |
| Incident title | 26 / 32, -0.015em | 600 |
| Section title | 24 / 30 | 600 |
| Answer headline | 22 / 28 | 600 |
| Panel title | 16 / 22 | 600 |
| Body | 15 / 22 | 400 |
| Row text | 14 / 20 | 400–500 |
| Meta | 13 / 19 | 400 |
| Caption | 12 / 18 | 400 |

**Shape and space.** Radius: panel 16, card or row 12, button 10, small chip 6, pill 999. Page max-width 1440 with 24px side padding. 16px gap between panels and 20px padding inside them. Touch targets at least 44px tall. Focus ring is 2px `--blue`, offset 2px.

**Motion.** Only three things move: the live dot (blink, 1.6s), the active pipeline step, and the blast-radius pulse on the failing node (scale 1 → 2.4 with fade, 2.4s). All three stop under `prefers-reduced-motion`.

## App shell (U01)

The top bar holds the logo (three nodes on a path, last node filled amber), the wordmark "PagerSage", and four nav links: War room, Company brain, Investigation, Actions. The current link gets the `--raised` background and `aria-current="page"`. On the right are a "Graph live" dot and the on-call person. Below 900px the nav wraps.

Suggested routes: `/` (war room), `/brain`, `/incidents/[id]/investigation`, `/incidents/[id]/actions`.

## Screens

### 1. War room (`design/Main.dc.html`): U01, U02/U03 incident view, U04, U05

The incident strip shows the severity pill, the id with opened time and age, the title, the current agent with a live dot, and a "Review actions" button that goes to Actions.

Below it are three panels that wrap on narrow screens: feed (`flex: 1 1 260px`), graph (`flex: 999 1 560px`), timeline (`flex: 1 1 360px`).

- **Incident feed (U05, `GET /incidents`)**: one row per incident with severity pill, age, title and the current agent in plain words ("Investigator is working"). The selected row gets the raised background. Footer note: alerts on related services within 10 minutes join the open incident (B02 merge rule).
- **Root-cause path (U02/U03, `GET /incidents/{id}`, `GET /graph`)**
  - Draw it with `<falkordb-canvas>`. Path nodes and edges are amber with a 3.5px stroke, other edges `#3A4366`, other nodes `--raised` fill with a `#4A5480` stroke.
  - The failing node gets a dark red fill and a short metric inside it ("40/40").
  - The rejected suspect is a dashed, dimmed box with a struck-through name.
  - Fragile nodes get a 3px `--danger` ring.
  - The "Blast radius" toggle (`aria-pressed`) shows dashed blue rings on the upstream services plus the pulse.
  - Under the canvas: the path as a breadcrumb of chips, then a legend.
- **Agent run (U04, SSE `/incidents/{id}/events`)**
  - Starts with a five-step pipeline bar (Triage, Investigator, Historian, Responder, Scribe): done is green, active is blue and blinking, queued is grey.
  - Each event type renders differently:
    - `alert`: amber icon tile, title, time.
    - `tool_call`: blue terminal icon, `tool_name(args)` in mono with the args muted, then a one-line result.
    - `decision`: `--raised` card reading "{Agent} decided" with the text. While streaming it gets an amber border and an "is deciding" dot. A rejected alternative goes on its own muted line.
    - `handoff`: a divider line reading "Handed to {Agent}".
    - `pending`: a dashed divider reading "{Agent} is next".
  - A "See the scores" link goes to Investigation.

### 2. Company brain (`design/CompanyBrain.dc.html`): U02 company view, U08

- **Ask box (U08, `POST /ask`)**: a labelled input with an amber Ask button, plus suggested questions as pill buttons. The answer panel has an amber border and `aria-live="polite"`. It shows the question, a headline answer, one paragraph, an "Evidence on the graph" list (label plus node ids in mono), and the query used in faint mono.
- **Graph (U02, `GET /graph`)**: nodes are colored by team and sized by criticality, with red rings for fragility and dashed outlines for services with no owner. Evidence node ids from `/ask` light their edges and rings in amber.
- **"Org chart / Who actually ships together" toggle (G18)**: recolors nodes by labelPropagation community. This is a stretch goal, so cut it first.
- **Insight panels** (most fragile, knowledge held by one person, no owning team): these use G05/G16 queries. They are not on the task board as UI tasks, so treat them as optional and ask before building.

### 3. Investigation (`design/Investigation.dc.html`): U06, U07

- **Suspects (U06)**: one selectable row per change, ranked by score. Each row has kind, author, time, title, a verdict pill (Cause = amber tint, Ruled out = grey, Decoy = red tint with the title struck through), the score in mono, and a bar scaled to the top score (amber for the cause, grey for the rest).
- **Score breakdown**: shows the four factors (recency, distance on the graph, fragility, anomaly now), each as "× value" with a one-line reason. Then the agent's reasoning in a raised card, and the formula in faint mono.
- **Memory (U07, G12)**: two columns, "Text similarity only" and "Re-ranked with the graph". The re-ranked column has an amber border, with reason chips ("same root service", "same change type", "up from 2nd").
- **Runbook card (G13)**: shows the runbook name, success squares and "Worked 3 of 3 times". Its button, "Use this runbook", goes to Actions.

### 4. Actions and Resolve (`design/Resolve.dc.html`): U09

- **Three action cards (B07, B08, B09)**:
  - Paged the owner: message preview and channel, plus who was chosen and why.
  - Opened an issue: link, repo and number, path chips.
  - Revert the change: shows the A10 policy line, with an amber border while waiting on the owner.
- **Rollback states**: `needs_ack` shows a "Record ack" button, `ready` shows an amber "Revert the change" button, and `done` shows a green confirmation line.
- **Resolve**: the button stays disabled until the rollback is done. After resolving, show the Scribe's postmortem in four short blocks: what happened, why, what fixed it, follow-up. Next to it, the runbook counter goes from 3/3 to 4/4, with the new square in amber.
- **Status pill**: Sev 1 open, then Mitigated, then Resolved.

## Build order

1. U01: tokens, fonts, shell, three-panel layout with stub data.
2. U05 feed, then U04 timeline.
3. U02 company graph, then U03 path highlight and blast pulse. Never cut U03: it is the demo.
4. U06 suspects, then U07 memory. Never cut similar-incident memory.
5. U09 actions and resolve.
6. U08 Ask with evidence highlighting.

## Accessibility checklist

- Every control is a real `<button>`, `<a>` or `<input>` with a `<label>`. Toggles use `aria-pressed`.
- Graph `<svg>`/canvas gets `role="img"` and an `aria-label` that states the path in words. The breadcrumb repeats the path as text.
- The answer panel and the score breakdown are `aria-live="polite"`.
- Colors that must be told apart also differ in lightness or carry a text label (verdict pills, severity pills, legend).
