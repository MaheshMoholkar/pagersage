# Day-1 contracts

Every workstream codes against these. The code is the source of truth; this page explains it.
Change a contract in its own commit.

| Contract | Code |
|---|---|
| Graph vocabulary, enums, IDs | `backend/pagersage/contracts/schema.py` |
| Agent event (SSE + Event nodes) | `backend/pagersage/contracts/events.py` |
| Kestrel Pay company file formats | `backend/pagersage/contracts/seed.py`, examples in `kestrel-pay/company/examples/` |
| Tool signatures and result types | `backend/pagersage/contracts/tools.py` |
| Named Cypher queries | `backend/pagersage/queries.py`, rules in `backend/queries/README.md` |

## 1. Graph schema

The node and edge model is [build-plan.md section 3](build-plan.md#3-final-graph-schema).
Use `Label` and `Rel` from `schema.py`; never type a label by hand. Changes from the plan:

- **`Commit.id` = `Commit.sha`.** Decision evidence is looked up by `id`; without this, commit
  evidence never linked (plan bug in T8b).
- **`Incident.status` adds `needs_human`**, used when an agent hits a refusal, the tool-call cap
  or a timeout.
- **`Event` nodes** store the agent events below: `id, incident_id, seq, ts, agent, kind,
  text, data (JSON string), highlight (JSON string)`. Graph properties can't hold maps.
- **`IMPACTS`** is written by the seed loader as the reverse of every `DEPENDS_ON`.

### IDs and time

| Node | id | Example |
|---|---|---|
| Service | `svc:<name>` | `svc:payments-db` |
| Team | `team:<slug>` | `team:payments` |
| Person | `person:<handle>` | `person:priya` |
| Deploy | `dep-<4 digits>` | `dep-0193` |
| ConfigChange | `cfg-<4 digits>` | `cfg-0061` |
| Commit | the sha | `a1b2c3d` |
| Incident | `INC-<3 digits>` | `INC-042` |
| Runbook | `rb:<slug>` | `rb:raise-payments-db-pool` |
| Policy | `pol:<slug>` | `pol:tier1-rollback-ack` |
| Event | `evt:<incident>:<seq>` | `evt:INC-107:3` |
| Alert | `alt-<5 digits>` | `alt-00042` |
| Postmortem | `pm:<incident>` | `pm:INC-042` |
| Agent | `agent:<name>` | `agent:investigator` |
| Decision | `dec:<incident>:<seq>` | `dec:INC-051:2` |
| Handoff | `ho:<incident>:<seq>` | `ho:INC-051:1` |

Timestamps are epoch seconds (int), in a property named `ts` unless the plan names it otherwise.

### FalkorDB 6.0.2 facts (tested in `backend/tests/test_falkordb.py`)

- Procedure names are case-insensitive: `algo.bfs` and `algo.BFS` both work.
- `algo.BFS` does **not** include the start node in `nodes` (answers G07's question).
- `//` comments work inside queries.
- **Bug:** a pattern comprehension that binds a relationship variable
  (`[(a)-[r:R]->(i) WHERE r.ok | ...]`) empties the comprehensions after it, and sometimes
  itself. Bind no relationship variables in comprehensions; use `OPTIONAL MATCH` + `collect`
  when you need an edge property.
- Data lives in `/var/lib/falkordb/data` in the container.
- The image's default query timeout is 1000 ms (`FALKORDB_ARGS ... TIMEOUT 1000`).

Found by `scripts/smoke_algos.py` (G01, `make smoke`; same checks in `test_smoke_algos`):

- **`db.idx.vector.queryNodes` yields cosine *distance*** (0 = identical, 2 = opposite), nearest
  first. `SimilarIncident.score` stays a similarity: G12 returns `1 - score`.
- **`algo.SSpaths` `pathCount` is the total number of paths, not per target.** `pathCount:1`
  returns only the single cheapest path. For one distance per reachable node use a large
  `pathCount` (e.g. 1000) and `min(pathWeight)` grouped by `last(nodes(path))` (G08).
- **Fractional `weightProp` values survive** in `algo.SPpaths` `pathWeight` (0.5 + 0.25 =
  0.75). Integer live weights (G09) still work; floats are allowed too.
- **Full-text fuzzy match is `%term%`** (edit distance 1); `%term%1` matches nothing. Prefix
  `pay*` works.
- `algo.labelPropagation`, `algo.wcc`, `algo.pageRank` and `algo.betweenness` (with
  `samplingSize`, `samplingSeed`) work with the signatures in build-plan.md section 1.
- **A null grouping key next to an aggregate crashes the server** (`RETURN c.status AS s,
  max(x.id)` with `c.status` unset: panic in `reply_compact`, the container exits). Wrap
  optional properties in `coalesce` in aggregating `RETURN`s. There's no test for this,
  since it would take CI's database down.

### Indexes and constraints (G02, `backend/pagersage/indexes.py`, `make indexes`)

| What | On |
|---|---|
| Range index + unique constraint | `id` on every `Label` |
| Range index | `Commit.sha` |
| Full-text | `Service(name, description)` |
| Vector, 384 dims, cosine | `Incident.embedding` |

`ensure_indexes(graph)` creates only what is missing and waits until the unique constraints are
enforced, so call it before writing to a fresh graph (the seed loader does, G03). A node
without `id` is still allowed; a second node with the same `id` raises "unique constraint
violation", so writers use `MERGE` on `id`. What FalkorDB 6.0.2 does (tested in
`backend/tests/test_indexes.py`):

- A repeated `CREATE INDEX` fails with "already indexed", so the setup reads `db.indexes()`
  and `GRAPH.CONSTRAINT LIST` first instead of retrying.
- A unique constraint needs an exact-match range index on the same property first, and builds
  asynchronously: `PENDING`, then `OPERATIONAL`, or `FAILED` when the data already has duplicates.
- A full-text index can gain fields one at a time (`ON (s.name)`, then `ON (s.description)`).
- A vector index with the wrong dimension can't be changed in place. `ensure_indexes` raises
  and says how to drop it.
- `db.indexes()` on a graph that does not exist yet raises "empty key".

## 2. Agent event

One line on the incident timeline. Emitted for every tool call, finding, decision, handoff and
action (A11), streamed over SSE (B04), stored as an `Event` node chained with `NEXT`.

```json
{
  "incident_id": "INC-107",
  "seq": 3,
  "ts": 1760000000,
  "agent": "investigator",
  "kind": "finding",
  "summary": "payments-db config change is the top suspect",
  "data": {"change_id": "cfg-0061", "score": 0.82},
  "highlight": {
    "nodes": ["svc:checkout-api", "svc:payments-db", "cfg-0061"],
    "edges": [["svc:checkout-api", "DEPENDS_ON", "svc:payments-svc"]]
  }
}
```

- `kind`: `status | tool_call | tool_result | finding | decision | handoff | action | error`.
  Agents emit one event per call (A11): `tool_call` is written once the call returns and
  carries its result size (`data = {tool, input, ok, rows}`), so `tool_result` is unused.
- `agent`: `triage | investigator | historian | responder | scribe | brain`, or null for system events
- `highlight` is what the graph canvas lights up.
- SSE framing: `id: <seq>`, `event: agent`, `data: <json>`. On reconnect the browser sends
  `Last-Event-ID`; the server replays events with a higher `seq` from the graph.

## 3. Kestrel Pay company files

PagerSage ingests these from `kestrel-pay/company/` (owned by Kestrel Pay, see
[`kestrel-pay/PLAN.md`](../kestrel-pay/PLAN.md); generated history is JSON Lines in
`kestrel-pay/history/export/`):

| File | Required | Holds |
|---|---|---|
| `topology.yaml` | yes | services (`name, tier 1-3, language, description, depends_on[to, calls_per_min, p99_ms]`) |
| `org.yaml` | yes | teams (`slug, name, slack_channel, owns[]`), people (`handle, name, team, role, timezone`), `on_call` (`start, rotation_days, teams{team: [handles]}`) |
| `runbooks.yaml` | no | `slug, title, service, steps[]` |
| `policies.yaml` | no | `slug, name, rule, actions[page/issue/rollback], max_tier` |

`load_seed_dir()` rejects: unknown dependency targets, self-dependencies, duplicate names,
services with zero or several owning teams, people in unknown teams, on-call handles from
another team, unknown timezones, runbooks for unknown services.

### History export (JSON Lines)

`load_history_dir(path, seed)` reads `kestrel-pay/history/export/`, one JSON object per line.
References are service names, person handles and change ids, never graph ids.

| File | Record | Becomes |
|---|---|---|
| `deploys.jsonl` | `id, service, version, ts, status (ok/rolled_back), env, deployed_by, commits[sha]` | Deploy, TARGETED, CONTAINS, DEPLOYED |
| `commits.jsonl` | `sha, message, author, ts, files_changed, lines_changed` | Commit, AUTHORED |
| `config_changes.jsonl` | `id, service, key, old, new, ts, made_by` (values are strings) | ConfigChange, CHANGED, MADE |
| `incidents.jsonl` | `id, title, severity, status, opened_at, resolved_at, summary, affected[], caused_by[{change, confidence}], alerts[{id, service, signal, value, threshold, severity, ts}], timeline[{ts, kind, text}], runbooks[{runbook, worked, ts}], resolved_by, postmortem{title, body, ts, author}` | Incident, AFFECTED, CAUSED_BY, Alert (FIRED_ON, PART_OF), Event chain (agent null), RESOLVED {ts, worked} from runbooks and from `resolved_by`, Postmortem (ABOUT, WROTE) |

It rejects: duplicate ids, deploys that ship unknown commits, commits shipped by zero or several
deploys, commits newer than their deploy, causes that name an unknown change, timeline or runbook
entries outside the incident window; with `seed`, also unknown services, people and runbooks.

### Seed loader (G03, `backend/pagersage/seed.py`)

`make seed` validates both directories, runs `ensure_indexes`, then writes everything with
`MERGE` on ids through `backend/queries/seed_*.cypher` (500 rows per statement, under the
image's 1000 ms query timeout). Seeding twice gives the same counts. `make reset`
(`reset_demo`) deletes the graph and seeds again, which drops everything a scenario injected.
Choices the files don't spell out:

- Every `Service` starts at `health: 1.0` and every `DEPENDS_ON` at `weight: 100`, the
  live-weight formula's value for a healthy service (G09).
- `IMPACTS` is written next to each `DEPENDS_ON`, in the same statement.
- `ON_CALL {from, to}` covers one full rotation per team from `on_call.start`: the i-th person
  in the rota is on call for the i-th shift (`to` is exclusive, UTC midnight).
- `Runbook.success_count` / `fail_count` are counted from past incidents' runbook outcomes.
- Timeline entries become `Event` nodes with `seq` from 1, `agent` unset, chained by `NEXT`.
- `(:Person)-[:RESOLVED]->(:Incident)` comes from `resolved_by`.
- Every past incident gets `embedding = vecf32(embed(incident_text(title, summary)))` (G04).

### Incident embeddings (G04, `backend/pagersage/embeddings.py`)

`embed(texts)` returns 384-dim, unit-length vectors from `sentence-transformers/all-MiniLM-L6-v2`
through fastembed (ONNX, no PyTorch). Embed every incident, past or new, from
`incident_text(title, summary)` so vectors compare like with like. The model (~90 MB)
downloads on first use into `$FASTEMBED_CACHE_PATH` (default: the system temp directory);
CI caches it. For the live pool-exhaustion text, vector search alone returns INC-019, INC-031,
INC-042 in that order: G12's graph re-ranking is what puts INC-042 first.

- `(:Person)-[:RESOLVED]->(:Incident)` comes from `resolved_by`.
- Every past incident gets `embedding = vecf32(embed(incident_text(title, summary)))` (G04).
, `backend/pagersage/algorithms.py`)

`seed_graph` ends with `run_batch`, which writes two scores onto every `Service` and checks
ownership:

| Property / check | Algorithm | Kestrel Pay result |
|---|---|---|
| `fragility` | `algo.betweenness` on `DEPENDS_ON`, `samplingSize` = service count | kafka 38, api-gateway 21 |
| `criticality` | `algo.pageRank('Service', 'DEPENDS_ON')` | kafka, then redis-cache |
| ownership gaps | `algo.wcc` over `Service` + `Team` on `OWNS` | none |
| `Person.community` (G18) | `algo.labelPropagation` on `COLLABORATES` | see below |

**Change from the plan:** the plan runs WCC over `OWNS` and `DEPENDS_ON`. `DEPENDS_ON` joins
nearly every service into one component that contains a team, so an unowned service would
not show up as a gap. WCC runs over `OWNS` only (tested in `tests/test_algorithms.py`).

**Real teams vs org chart (G18).** New relationship `(:Person)-[:COLLABORATES {deploys}]->(:Person)`
(`Rel.COLLABORATES`, one edge per pair, lower id first): their commits shipped in the same
deploy at least `MIN_SHARED_DEPLOYS = 3` times. At 1 or 2, a few cross-team deploys join nearly
everyone into one community. `algorithms.real_teams(graph)` lists the communities with each
member's org-chart team. Kestrel Pay: Payments, Risk & Identity and Ledger match the org chart;
**Platform and Checkout ship as one team**; **Merchant Experience is really two** (grace + kai;
omar + nina + lucy). Stable across runs (labelPropagation gave identical groups 9 times).

### Run-time ingest (B10, `contracts/ingest.py`)

`POST /ingest/deploy` (`DeployIn`: `id, service, version, ts, deployed_by, status?, env?,
commits[{sha, message, author, ts, files_changed?, lines_changed?}]`) and
`POST /ingest/config-change` (`ConfigChangeIn`: `id, service, key, old, new, ts, made_by`).
Names and handles, like the seed files. Both write with the seed loader's statements
(`MERGE` on ids, so a retry changes nothing) and return `{id, service_id}`. An unknown service
or person is a 400 (the seed statements would otherwise silently write nothing); a malformed
body is a 422.

### Alerts (B02, `POST /alerts`)

Alertmanager webhook JSON (version 4). For each **firing** alert PagerSage reads labels
`service`, `signal`, `severity` and annotations `value`, `threshold`, optional `health` (0-1);
resolved alerts are counted in `ignored`. Missing or bad fields are a 400 naming the field.
Each alert goes through `open_or_merge_incident`, then `update_live_weights` when it carries
`health`. Response: `{incidents: [{incident_id, alert_id, merged}], ignored}`.

- **Merge rule (change from the plan):** an alert joins an open incident opened in the last 10
  minutes with an alert on the **same service or one within 3 `DEPENDS_ON` hops** (either
  direction). The plan said same service only, which split pool-exhaustion into two
  incidents: payments-db saturating and checkout-api erroring 20 s later, two hops apart.
- New incidents: `INC-<n>` continuing the history (INC-051 first), status `open`, title from
  the alert; triage rewrites it. Alerts: `alt-<n>` (alt-00061 first). A merged alert raises
  the incident's severity when it is worse.
- Every alert appends a `status` event (`agent` null) to the incident's timeline.
- A **new** incident fires `runtime.incident_opened(incident_id)` in the background; the
  orchestrator (A03) registers with `@runtime.on_incident_opened`. Until then incidents wait in
  the graph.
- Ids, timeline `seq`s and handoff/decision numbers are "highest + 1", so `tools._write_lock`
  serialises those read-then-write steps between the API thread and agent threads.

### Incidents (B03)

- `GET /incidents?status=open&limit=50`: the feed, newest first. Each item: `{id, title,
  severity, status, opened_at, resolved_at, assigned_to (agent name or person handle), alerts
  (count), services (AFFECTED ids)}`. Past incidents are included (status `resolved`).
- `GET /incidents/{id}`: `{incident, summary, state (shared agent JSON), alerts, timeline
  (AgentEvents by seq), replay (replay_incident: decisions + handoffs), graph (as
  `/graph?incident=`: neighbourhood + highlight), postmortem ({title, body, ts} once the Scribe
  has written it, else null)}`. Unknown id: 400.

### Investigation screen (U06, U07; `pagersage/investigation.py`)

These are read-only: the Investigator's and Historian's reads, rerun so the UI can show every
score and not just the pick. Unknown id: 400.
- `GET /incidents/{id}/suspects`: `SuspectsView {alerting_service_id, since, suspects
  (Suspect[] with score_parts, best first), cause, rejected}`.
  - The ranking starts at the path's first service once the agents have stored `path`;
    before that, at the alerting service with the fewest callers (checkout-api, not
    payments-db).
  - `since` is the first alert minus 2 h, as the Investigator is told.
  - `cause` is the most confident `CAUSED_BY` (else `state.cause`); `rejected` is
    `state.rejected`.
- `GET /incidents/{id}/memory`: `MemoryView {path, similar (SimilarIncidents, or null before
  triage stores the embedding), runbook_service_id, runbooks}`.
  - `path` is `state.path`, else the AFFECTED services, else the alerting ones.
  - The runbook service is `state.cause_service`, else the alerting service with the most
    callers (payments-db).

### Live timeline (B04, `GET /incidents/{id}/events`)

Server-Sent Events, one message per `Event` node in `seq` order, framed as
`AgentEvent.to_sse()` (`id: <seq>`, `event: agent`, `data: <json>`). The stream replays events
after `Last-Event-ID` (or `?after=`), then tails the graph every 0.5 s, so it sees events from
any writer (alerts, handoffs, the A11 emitter, other processes) and resumes exactly after an
API restart. A `: keepalive` comment goes out after 15 s of quiet. `?follow=false` replays and
closes.

### Actions (B07-B09)

Action tools never raise on a failed send: they return `ActionResult(ok=False, detail=...)` so
the agent can carry on, and every attempt appends an `action` event (`data = {action, ok, url,
...}`) to the timeline. Bad input (unknown incident, handle, service, deploy) is a `ToolError`.

- **`page_owner` (B07):** posts to `DISCORD_WEBHOOK_URL`: incident id, severity, title, the
  person's name, handle and timezone, the alerting services, then the agent's message (cut to
  Discord's 2,000 characters; mentions disabled). No webhook set: not sent, `ok=False`.
- **`open_issue` (B08):** opens `[INC-…] title` in `GITHUB_ISSUES_REPO` with `GITHUB_TOKEN`; the
  body is the agent's text plus a footer built from the graph: incident, severity and title,
  then the root-cause path, suspect change and commits from the newest highlight that walks
  a `DEPENDS_ON` path (`root_cause_highlight`). Returns the issue URL. Missing credentials:
  not opened, `ok=False`.
- **`rollback` (B09, simulated):** the bad deploy gets `status: rolled_back`, as Kestrel Pay's
  history marks deploys that were undone, and a new `Deploy` of the service's previous good
  version (`simulated: true`, next `dep-` id) links to it: `(new)-[:ROLLED_BACK]->(old)`
  (`Rel.ROLLED_BACK`). Nothing outside the graph changes; say so in the README. (The board
  phrased it as a new deploy *with* `rolled_back`; that would contradict the history.)
  Refuses a deploy on another service, one already rolled back, or a first deploy.
- **`resolve_incident` (B09):** status `resolved`, `resolved_at`, `summary`; every service the
  incident's alerts fired on goes back to `health 1.0` (weights 100); a `status` event.
- **`revert_change` (U09, system function, `POST /incidents/{id}/revert {change_id}`):** a
  person reverts the incident's cause from the Actions screen (simulated).
  - A deploy goes through `rollback`.
  - A config change is marked `status: rolled_back`, and a new `ConfigChange` (next `cfg-`
    id, key set back, `simulated: true`) links to it with `(new)-[:ROLLED_BACK]->(old)`.
  - Either way: an `action` event `{action, ok, change_id}`, and the incident moves to
    `mitigated`.
  - Refused for a resolved incident, an unknown change, or one already reverted.
- `page_owner` events also carry `message`, and `open_issue` events carry `title`, for the
  Actions cards.
- Routes for the UI's action card: `POST /incidents/{id}/rollback {service_id, deploy_id}`
  (a person approved it; logs an `action` event) and `POST /incidents/{id}/resolve {summary}`,
  which then fires `runtime.incident_resolved` in the background for the Scribe (A08).

### Graph for the canvas (B06, `GET /graph`)

`{nodes, links, highlight}` (`graphview.GraphView`), shaped for `@falkordb/canvas`. A node is
`{id, name, kind (label), team?, tier?, criticality?, fragility?, health?}`; a link is
`{source, target, type, weight?, calls_per_min?}`.

- `GET /graph`: every service (owning team, tier, criticality, fragility, live health) and every
  `DEPENDS_ON` with live weight and traffic.
- `GET /graph?incident=INC-051`: the incident's alerting and `AFFECTED` services and their direct
  neighbours, its alerts (`FIRED_ON`), and every node and edge that its timeline events'
  `highlight` names (root-cause path, change, commits, people), with `highlight` = all of them
  merged in order. Unknown incident: 400.

### On call now (`GET /oncall`, `pagersage/oncall.py`)

`[{team, handle, name, until}]` (`oncall.OnCallNow`), one row per team whose rota has a shift
at the current time (`ON_CALL.from <= now < to`), by team name; `until` is when that shift
ends. `?at=` (epoch seconds) asks about another time; before the rota starts the list is empty.
The web top bar shows it.

## 4. Tools

Signatures, docstrings and return types are in `contracts/tools.py`; each stub names its task.
`AGENT_TOOLS` says which agent may call what. Pipeline agents finish by calling `handoff`.

| Agent | Tools |
|---|---|
| Triage | `find_service`, `blast_radius`, `set_triage`, `handoff` |
| Investigator | `suspect_changes`, `root_cause_path`, `record_cause`, `record_decision`, `handoff` |
| Historian | `similar_incidents`, `best_runbook`, `link_similar`, `record_decision`, `handoff` |
| Responder | `who_to_page`, `check_policy`, `page_owner`, `open_issue`, `rollback`, `record_decision`, `handoff` |
| Scribe | `replay_incident`, `best_runbook`, `write_postmortem`, `record_runbook_outcome` |
| Brain | `find_service`, `blast_radius`, `who_knows`, `bus_factor`, `fragile_services`, `replay_incident` |

System functions (API and orchestrator only): `open_or_merge_incident` (B02),
`update_live_weights` (G09), `resolve_incident` (B09), `mark_needs_human` (A03).

Rules: read tools use `graph.ro_query`; write tools are the only way agents change the graph;
return an empty list for "no data"; raise `ToolError` with a hint for bad input.

Tools are implemented in place in `contracts/tools.py` and get the graph from
`db.get_graph()`. Tests use the `tool_graph` fixture, which points that at one Kestrel Pay
graph seeded per test run (`seeded_graph`); tests that write take the `graph` fixture instead.

**`find_service` (G06).** Plain text is split into words, so `payments-db` isn't read as
RediSearch's "payments NOT db". Each word becomes `%word%` (typo-tolerant) at 4+ letters, or
`word*` below that, and any word may match. Names are searched first, then descriptions, so
`payments` returns payments-db and payments-svc ahead of reconciliation-job, whose description
says "payments" more often. Text with search operators (`pay*`) is used as given, scoped the
same way; an explicit `@field:` query runs unscoped.

**`blast_radius` (G07).** `algo.bfs` over `IMPACTS` from the service, up to `max_depth` (1-6)
hops, ordered by tier then criticality. The service itself is never included. Tools that take a
service id call `_require_service` first: an unknown id raises `ToolError` pointing at
`find_service`, while a known service with no callers (edge) returns `[]`.

**`suspect_changes` (G08).** One four-branch query (deploys and config changes, on the service
and downstream via `algo.SSpaths`), then Python scores each change:

| Part | Formula | Why |
|---|---|---|
| recency | `0.5 ** (age / 6 h)` | newer changes first |
| distance | `1 / (1 + hops)` | hops along `DEPENDS_ON` from the alerting service |
| fragility | `1 + fragility / max fragility` | betweenness, normalised to 1..2 |
| anomaly | `1 + 10 * max(0, worst_dep_health - health)` | how much sicker than everything below it |

`score` is the product; `score_parts` holds the four factors. **Changes from the plan:** the plan
scored `1/(1+dist)` on path weight and raw betweenness, and never defined `anomaly`. With healthy
weights of 5 per hop, payments-db (two hops away) got 1/11 of the decoy's distance factor, and
raw betweenness is 0 for a sink like payments-db; together the decoy always won. `dist` stays
the path weight in the result; the score uses hops. Anomaly is "a sick service whose
dependencies are sicker is a victim": checkout-api at health 0.4 above payments-db at 0.15
scores 1, payments-db scores 9.5. Pool-exhaustion result:

| Change | Service | recency | distance | fragility | anomaly | score |
|---|---|---|---|---|---|---|
| cfg-0061 pool cut | payments-db | 0.99 | 0.33 | 1.00 | 9.5 | **3.13** |
| decoy deploy | checkout-api | 1.00 | 1.00 | 1.44 | 1.0 | 1.44 |
| deploy shipping the commit | payments-svc | 0.99 | 0.50 | 1.24 | 1.0 | 0.61 |

**`update_live_weights` (G09, system function).** Sets `Service.health` from an alert and
`weight = live_weight(health) = clip(round(100 * health), 5, 100)` (an integer) on every
`DEPENDS_ON` edge into that service. **Change from the plan:** the plan wrote
`100 * (1 - health)`, which gives a sick service (0.15) weight 85 and a healthy one 5, so
shortest paths avoided the sick part of the system, the opposite of its stated intent.
Healthy edges are now 100 and sick ones cheap; the seed starts every edge at 100.

**`root_cause_path` (G10).** `algo.SPpaths` (`pathCount: 1`, live weights) from the alerting
service to the suspect's service, plus the change's details. A deploy brings its commits and
their authors; a config change brings the person who made it, and no commits (nothing in the
graph links a `ConfigChange` to the commit that edited `config.yaml`). `highlight` lists the
path's services, the change, its commits and people, and the edges between them:
`DEPENDS_ON` along the path, `TARGETED`/`CONTAINS`/`AUTHORED` for a deploy,
`CHANGED`/`MADE` for a config change. For pool-exhaustion: checkout-api → payments-svc →
payments-db, weight 115 (100 + 15). A suspect on the alerting service itself is a one-node
path of weight 0; a suspect that is not downstream raises `ToolError`.

**`who_to_page` (G11).** The owning team's on-call at `now` (`ON_CALL.from <= now < to`), then
the two people whose commits most recently shipped to the service in deploys at or before
`now`, newest first, ties by handle. Differences from the plan: a recent author's `team` is
their own team (`MEMBER_OF`), not `''`, and the on-call person is not listed again as an
author. payments-db on Oct 16: priya (on call), kwame, hana. ledger-svc: raj (on call), ines.

**`similar_incidents` (G12).** Vector search over the incident's own embedding (written at
triage; none yet raises `ToolError`) picks 10 candidates by text. The graph then ranks them:
services shared with the root-cause path, then whether the past cause hit a service on the
path, then newest first among candidates sharing any of the path, then text similarity.
`vector_only` is the same candidates by similarity alone. `runbooks` lists only runbooks that
worked on that incident. **Change from the plan:** the plan ranked by `sim + 0.15 *
shared_services`, but INC-019, INC-031 and INC-042 share the whole path and a pool cut on
payments-db, so that tie fell back to text and INC-019 won. The newest precedent reflects
today's config and runbook, and Kestrel Pay's scenario expects INC-042 first. Live
pool-exhaustion text: vector-only INC-019, INC-031, INC-042; graph-ranked INC-042, INC-031,
INC-019.

**`best_runbook` (G13).** A service's runbooks by `(success+1)/(success+fail+2)`, then success
count, then id. Smoothing keeps an untried runbook at 0.5 and stops one lucky run (0.67) from
beating a proven 3/3 (0.8). payments-db: raise-payments-db-pool 3/0, then failover 0/1.

**`record_decision` (G14).** Checks the incident, evidence ids and policy ids first (bad input
writes nothing), then runs the plan's three statements plus one: create the `Decision`
(`dec:<incident>:<n>`, `ABOUT`, `MADE_BY` an `Agent` created on first use with its model from
settings), `BASED_ON` each evidence node, `APPLIED_POLICY`, and `PRECEDENT_FOR` from decisions
on incidents this one is `SIMILAR_TO`. Evidence ids are matched without a label, which works
because ids are unique across labels. Past incidents have no `Decision` nodes (their
timelines are `Event`s), so precedents appear once a live incident has been decided and a
later one is linked to it.

**`handoff` (G15).** One read (state, last event `seq`, handoff count), then one write
statement, so a handoff lands whole or not at all: `Handoff` (`ho:<incident>:<n>`, `FROM`,
`TO`, `ON`), a `handoff` `Event` (next `seq`, `agent` = sender, `data` = `{from, to, note}`,
`NEXT` from the previous last event), `Incident.state` = stored JSON merged with
`state_patch` (top-level keys replace), and `ASSIGNED_TO` moved to the receiving agent. The
full note stays on the `Handoff`; the event text is cut to 300 characters.

**Company brain (G16).**
- `who_knows`: everyone tied to the service, scored `commits×1 + incidents_resolved×3 +
  postmortems_written×2 + team_member×2` (`EXPERT_WEIGHTS`; resolving or writing up an
  incident shows more than one commit). payments-db: priya (11 commits, 2 resolved, 2
  postmortems, on the team).
- `bus_factor`: services up to `max_tier` where one person authored every commit shipped in
  the last 90 days (Kestrel Pay's history window). Tier 1: ledger-svc, ines. A 30-day window
  would also flag kafka and others, so it stays at 90.
- `fragile_services`: by precomputed betweenness (G05), with criticality alongside. kafka first.

**`replay_incident` (G17).** One query (`backend/queries/replay_incident.cypher`, paste it into
FalkorDB Browser with `$iid` for the demo's proof beat) returns every decision with its maker,
evidence, precedents and policies, every handoff, and the timeline's event count. The tool
orders decisions and handoffs by time, then by their sequence number.

**`check_policy` (A10).** The `Policy` nodes seeded from `kestrel-pay/company/policies.yaml`
that list the action, on services whose tier is at most the policy's `max_tier` (no `max_tier`:
every tier), by id. Rollback on payments-db: `pol:no-database-rollback` and
`pol:tier1-rollback-ack`; any page: `pol:page-on-call-first`; an issue on a tier-3 service:
none. An unknown action or service is a `ToolError`.

## 5. Agents (`backend/pagersage/agents/`)

**Claude loop (A01, `agents/llm.py`).** `llm.run(agent, system, user, tools, finish=...)` is one
agent's tool-use loop. Model per agent from settings (`MODEL_TRIAGE`, ...); adaptive thinking on
every agent, effort `low` on Triage and Responder (Haiku 5.5); `tool_choice: auto`; no
temperature, top_p, top_k or prefill. The system prompt carries the cache breakpoint (tools sit
before it, so both are cached) and the top-level `cache_control` caches the conversation between
turns. `stop_reason` is checked first: `refusal` ends the run. Assistant content goes back
unchanged, thinking blocks included. A run ends when a `finish` tool succeeds (`handoff` for the
pipeline agents); an agent that stops without one is nudged once, then the run ends `no_finish`.
Limits: `MAX_TOOL_CALLS` 15 tool calls and `TIMEOUT` 180 s per run (`tool_cap`, `timeout`). Any
result other than `done` puts the incident in `needs_human` (A03). Tests script replies with
`tests/fake_claude.py`; nothing in CI calls the API.

**Tool registry (A02, `agents/registry.py`).** `tools_for(RunContext(agent, incident_id,
next_agent))` turns the agent's `AGENT_TOOLS` into strict Claude tools: the schema comes from
the signature, goes through `anthropic.transform_schema` (unsupported keywords such as
defaults move into the description), and `strict: true`. The orchestrator, not the model,
fills in `incident_id` (when the run has one), `agent` / `from_agent` and `to_agent`, so an
agent can only touch its own incident; `now` is never exposed. `handoff.state_patch` is sent as
the JSON string `state_patch_json`, because strict schemas need `additionalProperties: false` on
every object. Results go back as JSON (cut at 20,000 characters). These come back as
`is_error` results with a hint: a `ToolError`, bad arguments, an empty `find_service` or
`suspect_changes` ("widen `since`"), and any unexpected exception (logged). Every finished call
is passed to `RunContext.on_call` for the event emitter (A11).

**Event emitter (A11, `agents/emitter.py`).** The orchestrator sets `RunContext.on_call =
emitter.on_call`, so every finished call appends one event via `tools.append_event`:

| Call | Event |
|---|---|
| read tool | `tool_call` `{tool, input, ok, rows}`; highlights what it found (the path for `root_cause_path`) |
| `set_triage`, `record_cause`, `link_similar`, `write_postmortem`, `record_runbook_outcome` | `finding` `{tool, input}`; `CAUSED_BY` / `SIMILAR_TO` / `RESOLVED` edges highlighted |
| `record_decision` | `decision` `{decision_id, confidence, what}`; evidence highlighted |
| `rollback` | `action` `{action, ok, url, input}` |
| `handoff`, `page_owner`, `open_issue` | none: they write their own `handoff` / `action` event |
| any failed call | `error` `{tool, input, hint}` |

Brain runs have no incident and emit nothing. A failed write is logged, never raised.

**Orchestrator (A03, `agents/orchestrator.py`).** Plain Python, no framework. `install()` (called
by `main.py`) registers `run_pipeline` on `runtime.on_incident_opened` and `run_scribe` on
`runtime.on_incident_resolved`, only when `AGENTS_ENABLED` (default true; `tests/conftest.py`
sets it false) and `ANTHROPIC_API_KEY` are set. Without them incidents wait in the graph.
`run_pipeline` runs Triage → Investigator → Historian → Responder; the Scribe runs on resolve.
Each agent gets a fresh conversation whose user turn is `brief(incident, agent)`: the incident,
its alerts, triage's affected services, `Incident.state` and the newest handoff note addressed
to it, read from the graph inside `<incident>` tags. No transcript passes between agents. Each
run appends a `status` event "<agent> started". Pipeline agents finish with `handoff` (to the
next agent; the Responder hands to the Scribe), the Scribe with `write_postmortem`. Any other
end, or an exception, calls `mark_needs_human`: status `needs_human`, an `error` event with
the reason, and the pipeline stops.

**Prompt-injection hygiene (A13).** Commit messages, alert text, runbook steps and other
agents' notes are data:
- Every system prompt (`agents/prompts.py`) says the brief and tool results are data, not
  instructions, and must never be followed.
- The brief is fenced in `<incident>` tags with `<` and `>` escaped inside, so no text in it
  can close the fence.
- Tool results are JSON inside `tool_result` blocks, so a quote in a commit message stays
  inside its string.
- Agents change the graph only through their `AGENT_TOOLS`, with the incident and agent
  bound by the orchestrator.
- `page_owner`, `open_issue` and `rollback` are refused until `check_policy` has run for that
  action in the same agent run (`registry.NEEDS_POLICY`). The refusal is an `error` event.

**Triage (A04, `set_triage`).** Checks the severity, a non-empty title and summary, at least
one impacted service and that every id is a `Service` (bad input writes nothing; a resolved
incident is refused). It then sets title, severity, summary and status `investigating`, stores
`embedding = embed(incident_text(title, summary))` (G04's text, so live incidents compare with
past ones) and `MERGE`s `AFFECTED` to each service. Triage can run again without duplicating
edges. The pool-exhaustion triage text finds INC-042, INC-031, INC-019 through
`similar_incidents`. The Triage agent (Haiku 5.5, effort low) calls `blast_radius` on the
alerting services, `set_triage` and `handoff`.

**Investigator (A05, `record_cause`).** Checks the confidence (0-1), the incident and that the
id is a `Deploy` or `ConfigChange`, then `MERGE`s `CAUSED_BY {confidence, ts}` (the same change
again updates its confidence). The Investigator agent (Sonnet 5.5) calls `suspect_changes` on
the alerting service users hit, reads `score_parts` (anomaly above 1 = sicker than everything
below it), calls `root_cause_path` and `record_cause`, records a decision whose `why` names the
rejected decoy, and hands off `{cause, cause_service, path, rejected}`. Pool exhaustion:
cfg-0061 at 3.13 over the checkout-api decoy dep-0417 at 1.44.

**Historian (A06, `link_similar`).** Checks the score (0-1) and that both ids are different
incidents, then `MERGE`s `SIMILAR_TO {score}` (again: score updated) and back-fills
`PRECEDENT_FOR` from every decision on the past incident to the decisions already made on this
one (the Investigator's). Decisions recorded later get theirs in `record_decision`. Past
incidents have no `Decision` nodes (their history is `Event`s), so precedents link only between
live incidents. The Historian agent (Sonnet 5.5) calls `similar_incidents` with the root-cause
path, `link_similar` for the graph-ranked matches, `best_runbook` for the cause service and
records a decision. Pool exhaustion: INC-042, INC-031, INC-019, then
`rb:raise-payments-db-pool` (3/0).

**Responder (A07).** No new tools: the Responder agent (Haiku 5.5, effort low) calls
`who_to_page` for the cause service, `check_policy` for each action it plans (the registry
refuses `page_owner`, `open_issue` and `rollback` until then), pages the on-call, opens the
issue, rolls back only a deploy (`dep-`) that policy allows without an ack, records a decision
with `policy_ids` (`APPLIED_POLICY`) and hands off to the Scribe. Pool exhaustion: the cause is
a config change on a tier-1 database, so `pol:no-database-rollback` and
`pol:tier1-rollback-ack` rule out rollback; priya is paged and the issue opened.

**Scribe (A08, on resolve).** This closes the memory loop.
- **`write_postmortem`** needs a resolved incident and a non-empty title and body. It writes
  the incident's `Postmortem` (`pm:<incident>`, `ABOUT`; writing again replaces the text),
  `(Agent scribe)-[:WROTE]->` it, and refreshes `Incident.embedding` from the final title and
  summary, so the next `similar_incidents` finds this one.
- **`record_runbook_outcome`** `MERGE`s `Runbook -[:RESOLVED {ts, worked}]-> Incident` (again:
  updated, not added) and recounts `success_count` / `fail_count` from all of the runbook's
  `RESOLVED` edges, as the seed derives them. `rb:raise-payments-db-pool` goes 3/0 → 4/0
  after the demo resolve.
- **Contract change:** `WROTE` is now `(Person|Agent)->(Postmortem)`. `who_knows` still counts
  only people.
- **The Scribe agent** (Sonnet 5.5) runs from `runtime.on_incident_resolved`: `replay_incident`,
  `best_runbook`, `record_runbook_outcome` when a runbook was run, then `write_postmortem`,
  which ends its run. The body has exactly four markdown sections, `## What happened`, `## Why`,
  `## What fixed it` and `## Follow-up`, which the Actions screen shows as four blocks (U09).

**Brain (A09, `agents/brain.py`).** `brain.ask(question) -> AskOut {answer, evidence}`
(`contracts/ask.py`). The Brain agent (Sonnet 5.5) gets the read tools in
`AGENT_TOOLS[brain]` and a local strict `answer` tool `{answer, evidence_ids}` that ends the run.
Evidence ids must exist in the graph (`nodes_exist`); unknown ones go back as an error to fix
(people are `person:<handle>`). The question is fenced in `<question>` tags with `<` and `>`
escaped. There is no incident, so the Brain writes nothing and emits no events. No API key, a
refusal, the cap, a timeout or no `answer` raises `BrainError`.

**`POST /ask` (B05).** Body `AskIn {question}` (1-500 characters, no extra fields; else 422).
Returns `AskOut {answer, evidence}` from `brain.ask`; `evidence` is node ids for the canvas to
light. `BrainError` (no API key, or no answer) is a 503 `{"error"}`.

**Scenario evals (A12, `backend/evals/scenarios.py`, `make eval`).** Real Claude calls, run by
hand, never in CI. For each of pool-exhaustion, redis-down and inventory-slow:
1. Seed a throwaway graph `eval_<scenario>_<hex>` with Kestrel Pay.
2. Run the scenario's steps through the real API in-process. `inject.py` runs with its HTTP
   `post` sent to the app's TestClient and its git replaced, so no branch and no server. The
   clock is fixed after the history ends (`NOW`, inside the on-call rota).
3. Run the pipeline on the incident, resolve it and run the Scribe. Discord and GitHub calls are
   recorded, not sent.

A scenario **passes** when the incident's top `CAUSED_BY` is `expect.cause`. Also reported: the
decoy not blamed, the state's path vs `expect.path`, `SIMILAR_TO` vs `expect.similar`, the
runbook picked and its success count before and after, whether someone on `expect.page_team`
was paged, the postmortem title, status and run time. `--keep` keeps the graphs. The exit code
is non-zero when any cause is wrong.
