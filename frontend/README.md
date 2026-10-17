# PagerSage web

Next.js 16 + Tailwind 4. The design is in [`docs/ui-handoff/`](../docs/ui-handoff/): read
`HANDOFF.md` first, then open the screen's `.dc.html` (structure, copy, exact styles; don't copy
its `<script>`). Next 16 differs from older versions: check `node_modules/next/dist/docs/` before
using a Next API (see `AGENTS.md`).

```bash
make web                                   # http://localhost:3100 (or: npm run dev)
make db && make api                        # optional: the real backend on :8000
NEXT_PUBLIC_USE_STUBS=1 npm run dev        # force stub data
npm run lint && npm run build              # before every commit
```

Without a backend every page still renders: `lib/api.ts` falls back to the stub data and the
page shows a dashed "Stub data" badge.

## What's built

All four screens from the handoff, board tasks U01 to U09:

| Screen | Route | Parts | Data |
|---|---|---|---|
| War room | `/` (`?incident=`) | feed rail (U05, polls every 5 s); incident header and tabs; the verdict (cause, confidence, next step); root-cause path canvas with blast radius (U03); live agent run (U04, SSE) | `api.incidents`, `api.incident`, `useIncidentEvents` |
| Company brain | `/brain` (`?q=`) | Ask (U08) with the answer sliding in beside the company graph (U02), evidence lit on it | `api.graph`, `api.ask` |
| Investigation | `/incidents/[id]/investigation` | suspects + the score as an equation (U06); memory re-ranking itself from text to graph order, runbook card (U07) | `api.suspects`, `api.memory` |
| Actions | `/incidents/[id]/actions` | the response as steps (page, issue, ack, revert, resolve); the Scribe's postmortem and the runbook counter (U09) | `api.incident`, `api.revert`, `api.resolve` |

Where things live:
- **Tokens and motion** (`app/globals.css`, `app/layout.tsx`): colours as CSS variables *and*
  Tailwind colours (`bg-panel`, `text-muted`, `bg-amber`...), the `glass` / `glass-float` /
  `dot-grid` surfaces, the ambient glow, Geist, Geist Mono and Instrument Serif, and every CSS
  animation (`ps-ping`, `ps-shimmer-text`, `ps-skeleton`, `ps-beam`, `ps-runner`, `ps-sheen`,
  `ps-dash`)
  plus the route-transition CSS. All of it stops under reduced motion.
- **Shell** (`components/shell/`): the top bar (War room, Company brain, search, workspace,
  everyone on call from `GET /oncall`), the ⌘K command palette (`CommandPalette`: incidents,
  screens, Ask), `PageTransition`, which every page wraps its content in (except the Company
  brain, where only the graph moves), and `Now`: one clock for relative times, read on the
  server per request, so server and browser print the same "3 d" (no hydration mismatch).
  For the same reason animated bar widths go through `pct()`, which rounds.
- **Incident** (`components/incident/`): `IncidentHeader` with the Live / Investigation /
  Actions tabs (shared by three screens), and the agents' icons and `AgentBadge`.
- **Brand**: the logo is the one in [`docs/brand/`](../docs/brand/) (it replaces the handoff's
  three-node mark). `npm run brand` regenerates the favicon set from it: `app/icon.svg`,
  `favicon.ico`, `apple-icon.png`, `opengraph-image.png` and `public/icon-*.png` for
  `app/manifest.ts`. `components/shell/Logo.tsx` inlines the same mark: keep it in step.
- **Graph** (`components/graph/GraphCanvas.tsx`): one `<falkordb-canvas>` wrapper for every
  screen, with our own node drawing:
  - amber highlight with a glow and particles flowing along its edges, a failing node that
    breathes red, blast rings and ripples, fragility rings, rejected suspects;
  - flat nodes with a crisp ring and a core dot, in the owning team's colour on both screens
    (`colorBy="team"`), sized by criticality (Company brain) or by role (incident: path and
    failing nodes a size up, `sizeBy="role"`);
  - labels and strokes that keep their screen size at any zoom;
  - a zoom-in reveal when the layout settles, `fit` and `focus` (glide to a node); wheel and
    pinch zoom stay between 0.6× and 3.5× of the fitted zoom;
  - hover tooltips (node name, edge relationship) styled inside the component's shadow DOM,
    where float-tooltip's own stylesheet can't reach.

  `@falkordb/canvas` is pinned at exactly **0.2.9**. Releases 0.3.0 to 0.3.3 shipped on
  Oct 11–12 and add 3D (three.js), so upgrade deliberately.
- **Data** (`lib/`):
  - `types.ts` mirrors `docs/contracts.md`;
  - `api.ts` is the only place that fetches;
  - `stubs.ts` + `stubs/*.json` hold the pool-exhaustion scenario generated from the real
    backend;
  - `useIncidentEvents.ts` (SSE) and `usePolling.ts`;
  - `format.ts` has labels, times, team colours, `currentAgent()`, `rootCausePath()`,
    `withAlert()` and `failingNode()`.
- **UI kit** (`components/ui`): `index.tsx` has `SectionHeader`, `SevPill`, `StatusPill`,
  `Dot` / `LiveDot`, `Mono`, `Chip` (`found` = amber), `Kbd`, `Button`, `ButtonLink`
  (`primary` = amber), `StubBadge`, `Empty` and `TaskSlot`; `motion.tsx` has the animated
  ones: `Panel`, `Reveal`, `CountUp`, `Meter`, `Segmented` and `spotlight`.

## Design system

The handoff set the screens and their content. The look is a calm, cinematic control room:
ink and glass, light that means something, and motion that explains. Keep to these rules:

- **App shell** (`app/layout.tsx`): a 56px top bar, then `<main>`, which fills the rest of the
  window and scrolls. A page marked `fill` (`<PageTransition fill>`, the War room) gets exactly
  the remaining height on wide screens and splits it between panels that scroll inside
  themselves. Never size anything with `calc(100vh - <guess>)`.
- **Places, then the incident.** The top bar holds the two places (War room, Company brain)
  and search. Investigation and Actions belong to an incident: they are tabs in its header,
  next to its title. The one thing to do next sits where the answer is (the verdict's "Review
  the fix", the current step on Actions), in amber.
- **Surfaces:** a blue-black `bg` lit by a faint ambient glow; every region is a `Panel`
  (`glass`: translucent, a light top edge, soft shadow) with a 48px header (icon tile, title,
  count pill, actions), a body and an optional footer. `tone` lights a panel's top edge in a
  meaning colour. Things that float over content use `glass-float` (blur). Graphs sit in a
  `dot-grid` well. Lists are inset rounded rows with a hover surface; the selection is a
  surface that glides between rows (`layoutId`), not a border.
- **Type:** Geist 14px body; 13px rows and panel titles; 12px meta; 11px uppercase eyebrows;
  22–24px incident titles. Geist Mono, with tabular numbers, for ids, shas, scores, times and
  tool calls. Instrument Serif only for display moments (the brain hero, "Resolved in…").
- **Colour means something:**
  - amber: only what PagerSage found (path, evidence, the cause, the primary action);
  - blue: agent activity, selection and focus;
  - green: healthy or done;
  - red: severity and failure.

  Everything else is neutral.
- **Motion explains, never decorates:** panels and rows arrive in reading order (`Panel`
  `delay`, per-row delays), except where only the contents should move: the resolved verdict,
  the Agent run and Root-cause path panels (`Panel` `still`; timeline entries and the graph
  still animate) and the whole Company brain page, where only the graph moves; numbers count up (`CountUp`) and bars fill (`Meter`); selections and
  tabs slide; live things ripple (`LiveDot`), agents at work have a turning ring
  (`AgentBadge`); the root-cause path flows. Route changes fade up, incident tabs slide in
  their direction (`transitionTypes` on the link) and the incident header morphs in place.
  Springs are short (`SPRING`), eases are `EASE`. `MotionConfig reducedMotion="user"` plus the
  CSS media query turn it all off.
- **Controls:** `Button` / `ButtonLink` at `sm` 28px, `md` 32px or `lg` 40px, in `primary`
  (amber, with a sheen on hover), `secondary` or `ghost`; all press down slightly.
  `Segmented` for toggles; `SevPill`, `StatusPill`, `Chip`. Don't hand-roll new styles.
- **Graph canvas:** it shows only services plus the nodes that matter on that screen
  (`focusGraph`). Labels and strokes keep their screen size at any zoom, labels have a halo,
  and edge captions are off. Path chips and evidence rows glide the canvas to their node.
- **Accessibility:** real buttons, links and inputs; `aria-pressed` on toggles,
  `aria-current` on tabs and the current response step; `aria-live` on the verdict, answer,
  breakdown, memory list and timeline; the graph has `role="img"` plus a sentence; the
  palette is a `dialog` with a `combobox` and `listbox`; focus ring in blue.
- **Check every screen** at 1440×900, 1366×768 and 390px wide before committing a UI change.

## Known gaps

- **The owner's ack before a tier-1 revert is kept in the browser** (`ActionsView`), so a
  reload asks again. The backend has no ack record.
- **The workspace name and "Live" in the top bar are fixed text.** Who is on call comes
  from `GET /oncall` (one person per team).
- **Team colours:** the handoff names Payments, Checkout, Platform and Data. Kestrel Pay's
  teams are Payments, Checkout, Platform, Ledger, Risk & Identity and Merchant Experience.
  Ledger uses the "Data" pink; Risk and Merchant use placeholder colours until the designer
  picks them.
- **Not built (optional in the handoff):** the Company brain insight panels (most fragile,
  knowledge held by one person, no owning team) and the "Who actually ships together" toggle
  (G18).
- **Real Ask answers and the Scribe's postmortem need `ANTHROPIC_API_KEY`** on the backend.
  Without it, `/ask` returns 503 and the Actions page waits for a postmortem that never comes.
