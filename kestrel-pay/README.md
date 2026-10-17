# Kestrel Pay

Kestrel Pay is a **pretend payments company**, the customer PagerSage watches in the demo.
It is not running software. It is the company's memory written down as files, plus two scripts:
one that writes its past and one that breaks it live.

A real customer keeps these facts in their tools (service catalog, PagerDuty, GitHub, CD,
incident tracker). We have no customer, so each file below stands in for one of those tools.
PagerSage ingests them the way it would ingest a real company, and never writes back.

## What's in here

| Path | Stands in for | Example | Becomes in the graph |
|---|---|---|---|
| `company/topology.yaml` | Service catalog | checkout-api (tier 1) calls payments-svc 900×/min | `Service`, `DEPENDS_ON` |
| `company/org.yaml` | HR + PagerDuty | Priya is on Payments, on call Oct 12–18 | `Team`, `Person`, `OWNS`, `MEMBER_OF`, `ON_CALL` |
| `company/runbooks.yaml`, `policies.yaml` | Wiki | "Raise pool + restart payments-svc" | `Runbook`, `Policy` |
| `services/<name>/config.yaml` | The code repos | payments-db `max_pool_size: 200` | (the live scenario edits this file) |
| `history/export/*.jsonl` | GitHub + CD + incident tool, last 90 days | dep-0333, cfg-0050, INC-042 with postmortem | `Deploy`, `Commit`, `ConfigChange`, `Incident`, `Alert`, `Postmortem`… |
| `scenarios/*.yaml` | A bad day | Lower the pool to 60, then alerts | live HTTP calls to PagerSage |

The two scripts:

- `history/generate.py` writes the 90 days of history (~400 deploys, ~1,500 commits, 60
  config changes, 40 incidents). Same seed, same files. Prose comes from
  `history/text_cache.json`, written once by an LLM; generating makes no API calls.
- `scenarios/inject.py` plays a live incident. It acts as Kestrel Pay's CD pipeline and
  monitoring: it makes a real git commit, then tells PagerSage about the deploy, the config
  change and the alerts.

## How it flows

```
 SEED TIME  (make seed, in PagerSage)
   company/*.yaml + history/export/*.jsonl ──read──► PagerSage ──writes──► FalkorDB graph

 RUN TIME   (make inject SCENARIO=pool-exhaustion)
   inject.py ─► git commit on branch incident/pool-exhaustion-<time>   (working tree untouched)
             ─► POST /ingest/deploy          payments-svc ships the commit
             ─► POST /ingest/config-change   payments-db max_pool_size 200 → 60
             ─► POST /ingest/deploy          checkout-api decoy, a minute before the alerts
             ─► POST /alerts                 payments-db saturated, checkout-api erroring
                                              │
                         PagerSage agents walk the graph:
                         checkout-api → payments-svc → payments-db → cfg-0061 → commit → Tomás
                         "Same as INC-042; runbook 'Raise pool' worked 3/3; page Priya"
```

## The planted patterns (why the data looks the way it does)

The demo needs certain facts to be true so PagerSage has something smart to find. Tests
(`tests/test_history.py`) fail if any of them break.

1. **Repeat incident.** Lowering the payments-db pool caused INC-019, INC-031 and INC-042.
   The runbook "Raise pool + restart payments-svc" fixed all three. The live scenario does
   it a fourth time.
2. **Bus factor.** Only Inês has ever committed to ledger-svc.
3. **Fragility.** kafka has the highest betweenness: the most dependency paths run through it.
4. **Decoy.** checkout-api deploys more than any other service, and one of its deploys lands
   minutes before the pool alerts (INC-031, INC-042 and the live scenario), so "blame the
   latest deploy" gets it wrong.

## Common tasks

Run everything from `backend/` (Kestrel Pay uses the backend's Python environment):

```bash
cd backend
uv run python ../kestrel-pay/scenarios/inject.py pool-exhaustion --dry-run   # see the calls, no git/HTTP
uv run python ../kestrel-pay/history/generate.py      # after editing company/, services/*/config.yaml or text_cache.json
uv run python ../kestrel-pay/scripts/repo_files.py    # after editing company/ (service READMEs, CODEOWNERS)
uv run pytest ../kestrel-pay/tests                    # Kestrel Pay's own tests (also run by make test)
```

Scenarios: `pool-exhaustion` (the demo), `redis-down` and `inventory-slow` (for evals). Each
has an `expect:` block with the right answer: root cause, path, decoy, runbook and past incidents.

## Rules

- Kestrel Pay never imports `pagersage` and never touches FalkorDB. It only talks HTTP.
- Commit the regenerated `history/export/` with any change that affects it. Tests compare
  it byte for byte.
- Ids continue from the history (`dep-0416`, `cfg-0061`), so run `make reset` before
  injecting again.
- A real `make inject` creates a real `incident/…` branch; delete it after. Until PagerSage
  has its `/ingest/*` endpoints (task B10), use `--dry-run`.

More detail: [`PLAN.md`](PLAN.md) (design and tasks); file formats in
[`../docs/contracts.md`](../docs/contracts.md).
