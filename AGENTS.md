# PagerSage

Incident brain: when an alert fires, agents walk a FalkorDB graph of services, deploys,
commits, people and past incidents to find the likely root cause, page the owner and record
what fixed it. FalkorDB is the only datastore.

## Layout

```
backend/                  Python 3.12 API + agents (uv, FastAPI)
  pagersage/
    main.py               FastAPI app: /health + routers from routes/
    algorithms.py         batch: fragility, criticality, ownership gaps, real teams
    config.py             settings from env vars and repo-root .env
    db.py                 FalkorDB client, get_graph(), ping()
    embeddings.py         incident_text() + embed(): 384-dim MiniLM vectors via fastembed
    indexes.py            ensure_indexes(): range/full-text/vector indexes, unique ids
    queries.py            loads named Cypher from backend/queries/
    ingest.py             run-time ingest of deploys and config changes (B10)
    runtime.py            hooks the orchestrator registers: incident opened / resolved
    graphview.py          {nodes, links, highlight} for the canvas: company / incident
    incidents.py          incident feed and detail (B03)
    oncall.py             who is on call now, one person per team (web top bar)
    stream.py             SSE: replay after Last-Event-ID, then tail Event nodes (B04)
    routes/               HTTP routers, one module per area (thin: call tools/ingest)
    agents/               Claude agents
      llm.py              one agent's tool-use loop: models, caching, refusals, caps (A01)
      registry.py         contracts/tools.py as strict Claude tools, bound to one run (A02)
      emitter.py          one timeline event per tool call, decision and handoff (A11)
      prompts.py          one system prompt per agent, plus the shared data-not-instructions rules
      orchestrator.py     Triage → Investigator → Historian → Responder; Scribe on resolve (A03)
      brain.py            company-brain questions: read tools + answer with evidence ids (A09)
    seed.py               `make seed` / `make reset`: seed_graph(), reset_demo()
    contracts/            shared interfaces every part codes against
      schema.py           Label / Rel enums, status enums, ID helpers
      events.py           AgentEvent: SSE message + Event node
      seed.py             Kestrel Pay company file formats + validation
      ingest.py           /ingest/* and /alerts request formats
      ask.py              /ask question and answer
      tools.py            every agent tool signature (stubs) + AGENT_TOOLS
  evals/scenarios.py      `make eval`: Kestrel Pay scenarios through the real agents (A12)
  queries/                one Cypher statement per .cypher file
  tests/                  pytest; DB tests use a throwaway graph
  Dockerfile
frontend/                 Next.js 16 + Tailwind (read frontend/AGENTS.md, then frontend/README.md)
  app/                    routes: / (war room), /brain, /incidents/[id]/{investigation,actions}
  components/             ui kit, shell, one folder per screen
  lib/                    types.ts (API formats), api.ts (all fetching, stub fallback), stubs/
kestrel-pay/              separate project: the fictional company PagerSage watches
  README.md               start here: what the files stand for and how data flows
  PLAN.md                 its own plan
  company/                company YAML (examples/ shows the formats)
  services/<name>/        config.yaml (hand-written) + README.md (generated), CODEOWNERS
  history/                generate.py + text_cache.json -> export/*.jsonl (committed)
  scenarios/              <name>.yaml + inject.py (`make inject`)
  scripts/repo_files.py   regenerates service READMEs and CODEOWNERS
  tests/                  Kestrel Pay's own tests, run by `make test`; never import pagersage
scripts/                  one-off scripts
docs/                     build-plan.md, contracts.md, cypher.md, setup-accounts.md
docker-compose.yml        FalkorDB 6.0.2 + API
Makefile                  all common commands (`make help`)
```

## Commands

| Command | What |
|---|---|
| `make up` / `make down` | FalkorDB + API in Docker. API :8000, FalkorDB :6379, FalkorDB Browser :3000 |
| `make db` | Only FalkorDB, for running the API and tests on the host |
| `make api` | API on the host with reload |
| `make web` | Next.js dev server on :3100 |
| `make test` | Backend + Kestrel Pay tests (needs `make db`) |
| `make eval` | Scenarios end to end through the real agents (needs `make db` and `ANTHROPIC_API_KEY`; costs money; `EVALS=redis-down` for one) |
| `make lint` / `make fmt` | Ruff (backend + kestrel-pay) + ESLint / auto-format |
| `make catalogue` | Regenerate `docs/cypher.md` from `backend/queries/` |
| `make indexes` | Create missing indexes and unique `id` constraints (idempotent) |
| `make seed` / `make reset` | Ingest Kestrel Pay into the graph (idempotent) / delete the graph and seed again |
| `make inject SCENARIO=...` | Run a Kestrel Pay scenario: real git commit + HTTP calls to the API (`/ingest/*` is task B10) |

Backend only: `cd backend && uv run <cmd>`. Add dependencies with `uv add`, never pip.

Kestrel Pay scripts run in the backend env (stdlib + pyyaml only):
- `cd backend && uv run python ../kestrel-pay/scripts/repo_files.py`: regenerate service
  READMEs + CODEOWNERS after editing company YAML
- `cd backend && uv run python ../kestrel-pay/history/generate.py`: regenerate
  `history/export/` after editing company YAML, `services/*/config.yaml` or
  `text_cache.json`; commit the export
- `cd backend && uv run python ../kestrel-pay/scenarios/inject.py <name> --dry-run`: print a
  scenario's calls without git or HTTP

## Rules

- **Contracts first.** Code against `pagersage/contracts/`. Changing a signature, enum or
  format there is a deliberate change: update `docs/contracts.md` in the same commit.
- **Graph names come from enums.** Use `Label` and `Rel` from `contracts/schema.py`; never type
  a label or relationship string by hand.
- **IDs and time.** Every node has a human-readable unique `id` (`svc:payments-db`, `INC-042`,
  `dep-0193`; `Commit.id` is the sha). Timestamps are epoch seconds in `ts`.
- **Cypher.** One statement per file in `backend/queries/<name>.cypher`, `//` comment header,
  always `$params`, never string formatting. Read tools use `graph.ro_query`; only the write
  tools in `contracts/tools.py` change the graph.
- **Tool stubs** raise `NotImplementedError` naming the task that implements them. Keep the
  signature when implementing; the docstring is the tool description the model sees.
- **Kestrel Pay is a separate project.** It owns all company data, history and scenarios.
  PagerSage only ingests it: files at seed time, `/ingest/*` and `/alerts` over HTTP at run
  time. Kestrel Pay code never imports `pagersage` internals or writes to FalkorDB.
- **Tests.** DB tests take the `graph` fixture (a throwaway graph, deleted after). Read-only
  tool tests take `tool_graph` (one seeded Kestrel Pay graph per run; never write to it).
  Locally DB tests skip when FalkorDB is down; with `PAGERSAGE_REQUIRE_DB=1` (CI) they fail.
- **Style.** Ruff, line length 100, Python 3.12 syntax. Frontend follows its ESLint config.

## Gotchas

- **Planted demo patterns are tested** (`kestrel-pay/tests/test_history.py`): ledger-svc has
  one author (ines), kafka has the top betweenness, pool cuts caused INC-019/031/042,
  checkout-api is the decoy. Keep them true when editing company or history data.
- **Generated files are checked.** A stale export, README or CODEOWNERS fails the tests;
  rerun the two scripts above. Same for `docs/cypher.md` after adding or editing a query:
  `make catalogue`.
- **Generator must stay byte-identical:** never iterate a `set` unsorted (order changes with
  PYTHONHASHSEED); use the seeded `rng` only.
- **FalkorDB `algo.betweenness` is directed** (a pure sink scores 0) and samples source nodes
  unless you pass `samplingSize` >= node count.
- **History ends 2026-10-12;** live ids continue it (`dep-0416`, `cfg-0061`). Run `make reset`
  before injecting again.
- **Real `make inject` creates a real `incident/<name>-<time>` branch** in this repo (git
  plumbing; working tree untouched). `/ingest/*` (B10) and `/alerts` (B02) work; a new incident starts the agents
  when `ANTHROPIC_API_KEY` is set (A03).
- Kestrel tests import scripts with `conftest.load_script("history/generate.py")`, not package
  imports.

## Config

Copy `.env.example` to `.env` (gitignored). Settings live in `pagersage/config.py`:
FalkorDB host/port/credentials, graph name (`PAGERSAGE_GRAPH`), `ANTHROPIC_API_KEY`, per-agent
models (`MODEL_TRIAGE`, ...), `AGENTS_ENABLED` (agents on new incidents; tests set it false), Discord and GitHub action settings, `CORS_ORIGINS`. The embedding
model downloads once into `FASTEMBED_CACHE_PATH` (default: system temp dir). Inside Docker
Compose the API reaches FalkorDB at host `falkordb`.

## CI

`.github/workflows/ci.yml`: backend job runs ruff and pytest against a FalkorDB service
container (same image tag as Compose); frontend job runs `npm ci`, lint and build.
