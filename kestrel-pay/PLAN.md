# Kestrel Pay: Plan

Kestrel Pay is a fictional payments startup. It is the company PagerSage watches during the
demo. It owns everything a real company would: its services and their code, its teams and
people, on-call, runbooks, ~90 days of change and incident history, and the scenario that
breaks it.

PagerSage's plan is [`../docs/build-plan.md`](../docs/build-plan.md). This plan covers only
Kestrel Pay and the interface between the two.

## 1. Why it is separate

- PagerSage should work on a company it does not own. It **ingests** Kestrel Pay the way it
  would ingest a real customer: company files, change history, deploy events, alerts.
- Kestrel Pay never writes to FalkorDB. Only PagerSage does. That keeps the removal test honest
  and makes ingestion a real, demoable feature.
- The demo's bad commit is a real git commit in `kestrel-pay/services/`, so the root-cause path
  ends at a commit you can open.

## 2. The company

| | |
|---|---|
| Business | Card payments for online shops |
| Services | ~25: edge → api-gateway → checkout-api / user-api / search-api → payments-svc, ledger-svc, fraud-svc, notifications-svc → payments-db, ledger-db, redis-cache, kafka, … |
| Tiers | 1 (money path) to 3 (internal) |
| Teams | 6, ~30 people across timezones, weekly on-call rotations |
| History | 90 days: ~400 deploys, ~1,500 commits, ~60 config changes, 40 past incidents with alerts, timelines, postmortems and runbook outcomes |

### Planted patterns (the demo depends on these)

1. `payments-db` connection-pool config changes caused 3 past incidents (INC-042 is the most
   recent); runbook "Raise pool + restart payments-svc" worked 3/3. The live scenario repeats
   this.
2. One engineer is the only recent author on `ledger-svc` (bus-factor answer).
3. `kafka` has the highest betweenness (fragility answer).
4. A decoy: a noisy `checkout-api` deploy lands near the alert time, so PagerSage must use the
   graph, not just "latest deploy".

## 3. Layout

```
kestrel-pay/
  PLAN.md
  company/                    hand-written source of truth
    topology.yaml             services + DEPENDS_ON
    org.yaml                  teams, people, ownership, on-call
    runbooks.yaml
    policies.yaml
    examples/                 small format examples (validated by PagerSage's tests)
  services/<name>/            one stub folder per service: README.md + config.yaml
  CODEOWNERS                  generated from org.yaml, so the repo looks real
  history/
    generate.py               seeded generator: same seed, same history
    text_cache.json           LLM-written commit messages, postmortems, runbook text
    export/*.jsonl            generated history PagerSage ingests (committed)
  scenarios/
    pool-exhaustion.yaml      the live demo incident
    inject.py                 breaks Kestrel Pay and notifies PagerSage
```

## 4. Interface with PagerSage

The file formats are validated by PagerSage (`backend/pagersage/contracts/seed.py`), so a bad
Kestrel Pay file fails PagerSage's tests, not the demo.

**At seed time** (`make seed` in PagerSage) PagerSage reads:

| Source | Becomes |
|---|---|
| `company/topology.yaml` | Service, DEPENDS_ON, IMPACTS |
| `company/org.yaml` | Team, Person, OWNS, MEMBER_OF, ON_CALL |
| `company/runbooks.yaml`, `policies.yaml` | Runbook, FOR, Policy |
| `history/export/deploys.jsonl` | Deploy, TARGETED, CONTAINS, DEPLOYED |
| `history/export/commits.jsonl` | Commit, AUTHORED |
| `history/export/config_changes.jsonl` | ConfigChange, CHANGED, MADE |
| `history/export/incidents.jsonl` | Incident, Alert, Event, Postmortem, CAUSED_BY, AFFECTED, RESOLVED {worked} |

One JSON object per line. Field names match the node properties in build-plan.md section 3;
references use service names, person handles and ids (`dep-0193`, `INC-042`).

**At run time** the injector talks to PagerSage over HTTP only, like a CD system and
Alertmanager would:

| Call | When |
|---|---|
| `POST /ingest/deploy` | a deploy finished: `{id, service, version, ts, deployed_by, commits: [{sha, message, author, ts}]}` |
| `POST /ingest/config-change` | a config value changed: `{id, service, key, old, new, ts, made_by}` |
| `POST /alerts` | Alertmanager webhook JSON; labels `service`, `signal`, `severity`; annotations `value`, `threshold`, `health` (0-1) |

## 5. The live scenario: pool exhaustion

`scenarios/pool-exhaustion.yaml` describes it; `make inject SCENARIO=pool-exhaustion` runs it:

1. Commit the bad change on a fresh branch `incident/pool-exhaustion-<ts>`: lower
   `max_pool_size` in `services/payments-db/config.yaml`. Push the branch if you want the
   commit clickable on GitHub.
2. `POST /ingest/deploy` for `payments-svc` with that commit's real sha, plus
   `POST /ingest/config-change` for the pool size.
3. Post the decoy `checkout-api` deploy a minute earlier.
4. `POST /alerts`: `payments-db` health drops, then error-rate alerts on `checkout-api`
   (the symptom is two hops upstream of the cause).

`make reset` in PagerSage restores the seeded graph; the incident branch can be deleted.

## 6. Tasks

They replaced the old Kestrel Pay data tasks and the injector half of B10 on the PagerSage task board.

| # | Task | Done when |
|---|---|---|
| K1 | `company/topology.yaml` (~25 services) | Loads through PagerSage's validator; every service has a tier and description |
| K2 | `company/org.yaml` (6 teams, ~30 people, on-call) | Every service owned by exactly one team; rotations cover Oct 12–25 |
| K3 | `company/runbooks.yaml`, `policies.yaml` | 'Raise pool' runbook for payments-db; tier-1 rollback policy |
| K4 | `services/` stubs + generated CODEOWNERS | One folder per service; `services/payments-db/config.yaml` has `max_pool_size` |
| K5 | `history/generate.py` + `export/` with the four planted patterns | Same seed → byte-identical export; a test asserts each pattern |
| K6 | `history/text_cache.json` | One batch LLM call per entity type; committed; generation makes no API calls |
| K7 | `scenarios/pool-exhaustion.yaml` + `inject.py` | Running it produces a real commit and the three HTTP calls above |
| K8 | Two more scenarios (redis down, inventory slow) | Used by PagerSage's scenario evals (A12) |

PagerSage side, for reference: G03 becomes "ingest Kestrel Pay" (reads section 4's files), and
B10 becomes the `/ingest/deploy` and `/ingest/config-change` endpoints.

## 7. Order

K1 and K2 first: everything else is built from them. Then K3 and K4 in parallel with K5.
K6 after K5. K7 needs PagerSage's ingest endpoints (B10) to exist, or a stub that accepts them.
