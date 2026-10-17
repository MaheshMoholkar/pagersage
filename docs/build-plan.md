# PagerSage: Build Plan

Plan written Oct 7, 2026. Three goals: agents that act on connected data, agent memory and coordination, and a company brain you can ask.

> **One-line pitch:** An alert fires. PagerSage walks the service graph to the deploy, commit and person that most likely caused it, pages the right owner, cites the last time this happened, and writes down what fixed it so the next incident is faster.

> **Revision Oct 8 (review fixes):** T3 `suspect_changes` now also checks the alerting service when it has no downstream deps (UNION branch); T5 `who_to_page` UNION column names fixed and authors sorted by recency; T8 split into three queries so an empty evidence list no longer skips precedent linking; live weights stored as integers (docs list `pathWeight` as Integer); two extra smoke checks (vector `score` direction, integer `pathWeight`); model/embedding gotchas added; homelab section removed.

> **Revision Oct 11:** Triage and Responder move from `claude-haiku-4-5` to `claude-haiku-5-5`; model gotchas in section 2 rewritten for Haiku 5.5. Task breakdown lives in the PagerSage task board.

> **Revision Oct 11 (split):** Kestrel Pay is now its own project in `kestrel-pay/` with its own plan (`kestrel-pay/PLAN.md`) and owns all company data, history and scenarios. This plan covers PagerSage only; section 6 now describes what PagerSage ingests.

> **Revision Oct 11 (G01 smoke results):** `scripts/smoke_algos.py` ran every procedure against FalkorDB 6.0.2. Vector `score` is cosine **distance**, so T6 ranks on `1 - score`. `algo.SSpaths` `pathCount` caps the **total** number of paths, so T3 uses `pathCount:1000` + `min(pathWeight)` per service. Fractional weights survive in `pathWeight`. Fuzzy full-text is `%term%`, not `%term%1`. Details in `docs/contracts.md`.

---

## 1. Verified FalkorDB API (read this before writing any query)

Several names in the idea brief are wrong. Checked against docs.falkordb.com on Oct 7. The algorithm index page and the per-algorithm pages disagree in places; the per-algorithm code examples are what's listed here. **First step: run `scripts/smoke_algos.py`, which calls each of these once against a toy graph, so a wrong name fails in minute 5, not days later.**

| Use | Procedure (as in docs examples) | Signature / yields |
|---|---|---|
| Blast radius | `algo.bfs` | `CALL algo.bfs(startNode, maxDepth, 'REL_TYPE' or null) YIELD nodes, edges` (no direction arg; follows outgoing) |
| Root-cause path | `algo.SPpaths` | `CALL algo.SPpaths({sourceNode, targetNode, relTypes:[..], weightProp, costProp?, maxCost?, maxLen?, relDirection:'outgoing'/'incoming'/'both', pathCount}) YIELD path, pathWeight, pathCost` |
| Candidate causes | `algo.SSpaths` | same config minus `targetNode`; one source to all reachable nodes. `pathCount` caps the **total** paths returned, not per target |
| Fragile services | `algo.betweenness` (brief said `algo.betweenness-centrality`) | `CALL algo.betweenness({nodeLabels:[..], relationshipTypes:[..], samplingSize, samplingSeed}) YIELD node, score` |
| Critical services | `algo.pageRank` | `CALL algo.pageRank('Service','DEPENDS_ON') YIELD node, score` (scores from incoming edges) |
| Real teams | `algo.labelPropagation` (brief said `algo.cdlp`) | `CALL algo.labelPropagation({nodeLabels, relationshipTypes, maxIterations}) YIELD node, communityId` |
| Orphan check | `algo.wcc` | `CALL algo.wcc({nodeLabels, relationshipTypes}) YIELD node, componentId` |
| Similar incidents | vector index | `CREATE VECTOR INDEX FOR (i:Incident) ON (i.embedding) OPTIONS {dimension:384, similarityFunction:'cosine'}`; store with `vecf32([...])`; query `CALL db.idx.vector.queryNodes('Incident','embedding',5,vecf32($v)) YIELD node, score` |
| Name lookup | full-text index | `CREATE FULLTEXT INDEX FOR (s:Service) ON (s.name, s.description)`; `CALL db.idx.fulltext.queryNodes('Service', $q) YIELD node, score` (supports `pay*`, fuzzy `%paymnts%`; `%paymnts%1` matches nothing) |

Not needed: `algo.astar` (spatial), `algo.msf`, `algo.maxflow`, harmonic centrality (could not confirm its exact name; skip it).

Two more things `smoke_algos.py` must check, because the docs are ambiguous:
- **Vector `score` direction.** The docs don't say whether `db.idx.vector.queryNodes` returns cosine *similarity* (higher = closer) or *distance* (lower = closer). T6 ranks with `ORDER BY score + 0.15*shared_services DESC`, which assumes similarity. Insert two near-identical vectors and one opposite vector and assert which way `score` goes; flip T6's formula if needed.
- **`pathWeight` type.** The `algo.SPpaths` docs list `pathWeight` as Integer. Assert whether fractional `weightProp` values survive; until proven, store weights as integers (see the live-weight trick in section 4).

Ecosystem pieces worth using:
- **`@falkordb/canvas`** (npm): `<falkordb-canvas>` web component, force/tree/radial layouts, `isNodeSelected` / `isLinkSelected` callbacks for highlighting the traversed path. This is the demo's centrepiece.
- **FalkorDB Browser** (ships with the `falkordb/falkordb` Docker image on port 3000) for browsing the raw graph.
- Optional: **FalkorDB-MCPServer**, so the README can show "point Claude Desktop at the same brain". Cheap bonus, at the end.
- Deliberately **not** using Graphiti / GraphRAG-SDK / mem0 as the core. They would own the schema, and the point of the project is a graph model of my own. Hand-written schema plus hand-written Cypher is the stronger story. (Mention in README that they were considered and why.)

## 2. Architecture

```
            ┌───────────────────────── Web UI (Next.js + @falkordb/canvas) ─────────────────────────┐
            │  Incident feed │ live graph with highlighted path │ agent timeline (handoffs, tool calls) │
            └──────────────▲───────────────────────────────────────────────▲─────────────────────────┘
                           │ SSE stream of agent events                    │ REST
┌──────────────────────────┴───────────────────────────────────────────────┴───────────────────────┐
│ FastAPI backend                                                                                  │
│   /alerts (webhook, Alertmanager-compatible JSON)  /incidents  /ask (company-brain Q&A)          │
│                                                                                                  │
│   Orchestrator (plain Python state machine, no agent framework)                                  │
│     Triage ──► Investigator ──► Historian ──► Responder ──► Scribe                               │
│        every handoff = a (:Handoff) node + Incident.state update, all in FalkorDB                │
│                                                                                                  │
│   Tool layer: each tool is ONE named Cypher query from queries/*.cypher (also listed in README)  │
└──────────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                               │ falkordb-py
                                    ┌──────────▼──────────┐       ┌───────────────────────────┐
                                    │ FalkorDB (Docker)   │       │ Actions: GitHub issue,    │
                                    │ graph "pagersage"   │       │ Discord/Slack webhook page│
                                    └─────────────────────┘       └───────────────────────────┘
```

Removal test: delete FalkorDB and nothing works. Topology, ownership, deploy history, memory, agent shared state and handoffs all live only in the graph. There is no Postgres and no separate vector DB.

Data comes from Kestrel Pay (`kestrel-pay/`, section 6): company files and history at seed time, deploys and alerts over HTTP at run time.

**Stack (recommended):** Python 3.12, FastAPI, `falkordb` Python client, Anthropic SDK with tool use. Next.js + `@falkordb/canvas` front end. Docker Compose for local; deploy backend + FalkorDB on one small VPS or Railway/Fly, frontend on Vercel (or serve the built frontend from FastAPI to keep it to one box).

**Models:** `claude-sonnet-5-5` for Investigator, Historian and Scribe (multi-step reasoning), `claude-haiku-5-5` for Triage and Responder (fast, cheap: $0.10 / $0.50 per MTok for prompts up to 100K tokens). Embeddings: a local model (`sentence-transformers/all-MiniLM-L6-v2`, 384 dims) so there is no second API key and the demo works offline-ish. Fix the dimension in the vector index to match.

**Model gotchas (check before building the agents):**
- `claude-haiku-5-5` runs adaptive thinking **by default**. Control depth with `output_config: {effort: ...}` (default `medium`; use `low` for Triage and Responder). `thinking: {type: "enabled", budget_tokens: N}` returns a 400. `thinking: {type: "disabled"}` is accepted only at effort `high` or below.
- Both models can start a response with `thinking` blocks: read content blocks by `type`, never `content[0].text`, pass thinking blocks back unchanged with tool results, and leave `max_tokens` room for thinking.
- `claude-haiku-5-5` rejects non-default `temperature` / `top_p` / `top_k` and assistant prefill (400). Get output format from `strict: true` tools or structured outputs instead.
- `claude-sonnet-5-5` rejects forced `tool_choice` (`any` / `tool`) with a 400. Haiku 5.5 accepts it but then skips thinking. Use `tool_choice: auto` on both, tell the agent in the prompt to finish by calling `handoff`, and set `strict: true` on the tool schema. Sonnet 5.5 thinking can't be set to `disabled` (use `between_tools` if you need it off).
- Refusals: always check `stop_reason` before reading content; on `refusal` mark the incident `needs_human`. Sonnet 5.5 can reroute with `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`); Haiku 5.5 has **no** server-side fallback.
- Put the stable system prompt and tool list first and cache them; each agent loops several times per incident. Haiku 5.5's minimum cacheable prefix is 512 tokens (was 4,096 on Haiku 4.5), so short agent prompts now cache too.

**Embedding footprint:** `sentence-transformers` pulls in PyTorch, which bloats the deploy image. Consider `fastembed` (ONNX runtime) with the same `all-MiniLM-L6-v2` model (384 dims) for the deployed backend.

**Why no agent framework:** a ~150-line orchestrator is easy to read and explain, and every step is persisted to the graph anyway. LangGraph etc. would hide the agent coordination this project is about.

## 3. Final graph schema

Conventions: timestamps are epoch seconds (`ts`), IDs are human-readable (`svc:payments-api`, `INC-042`, `dep-0193`).

### Nodes

| Label | Key properties |
|---|---|
| `Service` | `id, name, tier (1-3), language, description, criticality (pageRank), fragility (betweenness), health (0-1, live)` |
| `Team` | `id, name, slack_channel` |
| `Person` | `id, name, handle, timezone, role` |
| `Deploy` | `id, version, ts, status ('ok'/'rolled_back'), env` |
| `Commit` | `sha, message, ts, files_changed, lines_changed` |
| `ConfigChange` | `id, key, old, new, ts` |
| `Alert` | `id, ts, signal ('error_rate','latency_p99','saturation'), value, threshold, severity` |
| `Incident` | `id, title, severity, status ('open','investigating','mitigated','resolved'), opened_at, resolved_at, summary, embedding (vecf32), state (JSON string: shared agent scratchpad)` |
| `Runbook` | `id, title, steps (list of strings), success_count, fail_count` |
| `Postmortem` | `id, title, body, ts` |
| `Decision` | `id, what, why, ts, confidence` |
| `Policy` | `id, name, rule` (e.g. "Tier-1 rollback requires owner ack") |
| `Agent` | `name ('triage','investigator',...), model` |
| `Handoff` | `id, ts, note` |
| `Event` | `id, ts, kind, text` (incident timeline = episodic memory) |

### Relationships

```
(:Service)-[:DEPENDS_ON {calls_per_min, p99_ms, weight}]->(:Service)   // a calls b
(:Service)-[:IMPACTS]->(:Service)                                       // materialised reverse of DEPENDS_ON, see note
(:Team)-[:OWNS]->(:Service)
(:Person)-[:MEMBER_OF]->(:Team)
(:Person)-[:ON_CALL {from, to}]->(:Team)
(:Deploy)-[:TARGETED]->(:Service)
(:Deploy)-[:CONTAINS]->(:Commit)
(:Person)-[:AUTHORED]->(:Commit)
(:Person)-[:DEPLOYED]->(:Deploy)
(:ConfigChange)-[:CHANGED]->(:Service)
(:Person)-[:MADE]->(:ConfigChange)
(:Alert)-[:FIRED_ON]->(:Service)
(:Alert)-[:PART_OF]->(:Incident)
(:Incident)-[:CAUSED_BY {confidence}]->(:Deploy|:ConfigChange)
(:Incident)-[:AFFECTED]->(:Service)
(:Incident)-[:SIMILAR_TO {score}]->(:Incident)
(:Runbook)-[:FOR]->(:Service)
(:Runbook)-[:RESOLVED {ts, worked}]->(:Incident)      // procedural memory
(:Postmortem)-[:ABOUT]->(:Incident)
(:Person)-[:WROTE]->(:Postmortem)
(:Person)-[:RESOLVED]->(:Incident)
(:Event)-[:PART_OF]->(:Incident) ; (:Event)-[:NEXT]->(:Event)            // episodic timeline
(:Decision)-[:ABOUT]->(:Incident)
(:Decision)-[:BASED_ON]->(evidence: Deploy|Commit|Incident|Runbook)
(:Decision)-[:PRECEDENT_FOR]->(:Decision)
(:Decision)-[:APPLIED_POLICY]->(:Policy)
(:Decision)-[:MADE_BY]->(:Agent|:Person)
(:Handoff)-[:FROM]->(:Agent) ; (:Handoff)-[:TO]->(:Agent) ; (:Handoff)-[:ON]->(:Incident)
(:Incident)-[:ASSIGNED_TO]->(:Agent|:Person)
```

**Why `IMPACTS` exists:** `algo.bfs` has no direction argument. Blast radius needs "who calls me" (incoming `DEPENDS_ON`), so we keep a reverse edge and BFS over it. Good thing to explain in the README: a modelling choice made for an algorithm.

**Memory layers mapped to the schema** (worth stating in the README):
- Episodic: `Event` chains + `Incident` nodes with embeddings.
- Semantic: the topology, ownership and expertise facts (`DEPENDS_ON`, `OWNS`, `AUTHORED`).
- Procedural: `Runbook` + `RESOLVED {worked}` edges with success counts, which rank runbooks next time.
- Decision traces: `Decision` nodes with `BASED_ON` evidence and `PRECEDENT_FOR` links (FalkorDB's own "context graph" story).

## 4. Agent tools = named Cypher queries

Each lives in `backend/queries/<name>.cypher`, is exposed as one Claude tool, and is listed in the README with a one-line explanation. Parameters are `$params`, never string-formatted.

**T1. `find_service`**: entry point from free text.
```cypher
CALL db.idx.fulltext.queryNodes('Service', $q) YIELD node, score
RETURN node.id, node.name, score ORDER BY score DESC LIMIT 3
```

**T2. `blast_radius`**: who is hurt if this service is down.
```cypher
MATCH (s:Service {id:$sid})
CALL algo.bfs(s, 3, 'IMPACTS') YIELD nodes
UNWIND nodes AS n
OPTIONAL MATCH (t:Team)-[:OWNS]->(n)
RETURN n.id, n.tier, t.name ORDER BY n.tier
```

**T3. `suspect_changes`**: recent deploys/config changes on the alerting service *and everything it depends on* (the root cause is usually downstream of the symptom).
```cypher
// branch 1: the alerting service itself (dist 0). Separate branch because if the
// service has no outgoing DEPENDS_ON, SSpaths yields zero rows and would drop it.
MATCH (svc:Service {id:$sid})<-[:TARGETED]-(d:Deploy)
WHERE d.ts > $since
OPTIONAL MATCH (d)-[:CONTAINS]->(cm:Commit)<-[:AUTHORED]-(p:Person)
RETURN svc.id AS svc_id, d.id AS deploy_id, d.ts AS ts, 0 AS dist, svc.fragility AS fragility,
       collect(DISTINCT {sha:cm.sha, msg:cm.message, author:p.handle}) AS commits
UNION
// branch 2: everything downstream of it (root cause is usually downstream of the symptom)
MATCH (s:Service {id:$sid})
CALL algo.SSpaths({sourceNode:s, relTypes:['DEPENDS_ON'], relDirection:'outgoing',
                   weightProp:'weight', maxLen:4, pathCount:1000})
YIELD path, pathWeight
// pathCount is a total, not per target: keep the cheapest path to each service
WITH last(nodes(path)) AS svc, min(pathWeight) AS dist
MATCH (d:Deploy)-[:TARGETED]->(svc) WHERE d.ts > $since
OPTIONAL MATCH (d)-[:CONTAINS]->(cm:Commit)<-[:AUTHORED]-(p:Person)
RETURN svc.id AS svc_id, d.id AS deploy_id, d.ts AS ts, dist, svc.fragility AS fragility,
       collect(DISTINCT {sha:cm.sha, msg:cm.message, author:p.handle}) AS commits
```
Both `UNION` branches must return identical column names. Cypher can't `ORDER BY` across a whole `UNION`, so sort in Python (the ranking happens there anyway). Run the same with `ConfigChange` as two more `UNION` branches. Python ranks suspects with a simple, explainable score: `recency × (1/(1+dist)) × (1+fragility) × anomaly(svc)`. Show the score breakdown in the UI.

**The live-weight trick:** when alerts arrive we set `DEPENDS_ON.weight = toInteger(round(100 * target.health))` clipped to [5, 100] (fixed in G09: the original `100 * (1 - health)` made sick services expensive) (integers, because the docs list `pathWeight` as Integer; switch back to floats only if `smoke_algos.py` proves they work). Unhealthy services become "cheap" to walk through, so the shortest path naturally runs through the sick part of the system. This is the line that makes the graph do real work, so call it out in the demo.

**T4. `root_cause_path`**: the exact path to highlight on screen.
```cypher
MATCH (a:Service {id:$alerting}), (b:Service {id:$suspect})
CALL algo.SPpaths({sourceNode:a, targetNode:b, relTypes:['DEPENDS_ON'],
                   relDirection:'outgoing', weightProp:'weight', pathCount:1})
YIELD path, pathWeight
MATCH (d:Deploy {id:$deploy})-[:CONTAINS]->(c:Commit)<-[:AUTHORED]-(p:Person)
RETURN [n IN nodes(path) | n.id] AS services, pathWeight, d.id, collect(c.sha), collect(DISTINCT p.handle)
```
UI highlights `Alert → services… → Deploy → Commit → Person`.

**T5. `who_to_page`**: owner on call now, with an expert fallback.
```cypher
MATCH (s:Service {id:$sid})<-[:OWNS]-(t:Team)<-[oc:ON_CALL]-(p:Person)
WHERE oc.from <= $now AND oc.to > $now
RETURN p.handle AS handle, t.name AS team, 'on_call' AS reason
UNION
MATCH (s:Service {id:$sid})<-[:TARGETED]-(d:Deploy)-[:CONTAINS]->(:Commit)<-[:AUTHORED]-(p:Person)
WITH p, max(d.ts) AS last_ts ORDER BY last_ts DESC LIMIT 2
RETURN p.handle AS handle, '' AS team, 'recent_author' AS reason
```
(`UNION` requires identical column names in both branches; the original `t.name` vs `t` would error. Recent authors are now the two most recent, not arbitrary.)

**T6. `similar_incidents`**: hybrid retrieval. Vector search finds candidates, graph re-ranks them.
```cypher
CALL db.idx.vector.queryNodes('Incident', 'embedding', 10, vecf32($v)) YIELD node AS i, score
OPTIONAL MATCH (i)-[:AFFECTED]->(s:Service) WHERE s.id IN $path_services
OPTIONAL MATCH (rb:Runbook)-[r:RESOLVED {worked:true}]->(i)
OPTIONAL MATCH (pm:Postmortem)-[:ABOUT]->(i)
WITH i, 1 - score AS sim, count(DISTINCT s) AS shared_services,
     collect(DISTINCT {rb:rb.id, title:rb.title, ok:rb.success_count}) AS runbooks,
     collect(DISTINCT pm.title) AS postmortems
RETURN i.id, i.title, sim, shared_services, runbooks, postmortems
ORDER BY sim + 0.15*shared_services DESC LIMIT 3
```
`score` from the vector index is cosine distance (checked by `smoke_algos.py`), so `1 - score` is the similarity. Show both orderings (vector-only vs graph re-ranked) in the UI or the blog: a cheap, convincing "graph beats vector" moment.

**T7. `best_runbook`**: procedural memory.
```cypher
MATCH (rb:Runbook)-[:FOR]->(:Service {id:$sid})
RETURN rb.id, rb.title, rb.steps, rb.success_count, rb.fail_count
ORDER BY (rb.success_count+1.0)/(rb.success_count+rb.fail_count+2.0) DESC LIMIT 3
```

**T8. `check_policy` / `record_decision`**: decision traces.
Three queries, run in order by one Python function. (As a single query, an empty `$evidence` list made `UNWIND` produce zero rows, so the precedent link was silently skipped.)
```cypher
// 8a. record the decision
MATCH (i:Incident {id:$iid}), (a:Agent {name:$agent})
CREATE (d:Decision {id:$did, what:$what, why:$why, ts:$now, confidence:$conf})
CREATE (d)-[:ABOUT]->(i), (d)-[:MADE_BY]->(a)

// 8b. link evidence (Python skips this call when $evidence is empty)
MATCH (d:Decision {id:$did})
UNWIND $evidence AS eid
MATCH (e) WHERE e.id = eid
MERGE (d)-[:BASED_ON]->(e)

// 8c. precedent: link to decisions taken on similar past incidents
MATCH (d:Decision {id:$did})-[:ABOUT]->(:Incident)-[:SIMILAR_TO]->(:Incident)<-[:ABOUT]-(prev:Decision)
MERGE (prev)-[:PRECEDENT_FOR]->(d)
```

**T9. `handoff`**: agent coordination. Writes a `Handoff` node, appends an `Event`, merges JSON into `Incident.state`, flips `ASSIGNED_TO`.

**T10. Company-brain questions** (`/ask` endpoint, Responder agent):
- "Who knows the payments DB?": rank people by commits to it + incidents resolved on it + postmortems written + team membership (one `MATCH … OPTIONAL MATCH … count()` query with weights).
- "What breaks if checkout-api goes down?": T2.
- "Who is our bus factor?": people who are the sole recent author on a tier-1 service.
- "Which services are fragile?": precomputed `fragility` from `algo.betweenness`.

**Batch jobs (run on seed and nightly):**
```cypher
CALL algo.betweenness({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON'], samplingSeed:42})
YIELD node, score SET node.fragility = score;
CALL algo.pageRank('Service','DEPENDS_ON') YIELD node, score SET node.criticality = score;
CALL algo.wcc({nodeLabels:['Service','Team'], relationshipTypes:['OWNS','DEPENDS_ON']})
YIELD node, componentId  // services with no team in their component = ownership gaps
```
Optional company-brain insight: `algo.labelPropagation` over a derived `(:Person)-[:COLLABORATES {n}]-(:Person)` edge (co-authored deploys) to show "real teams vs org chart".

## 5. Agents and handoffs

| Agent | Model | Tools | Writes |
|---|---|---|---|
| Triage | haiku | find_service, blast_radius | creates Incident, severity, Event |
| Investigator | sonnet | suspect_changes, root_cause_path | `CAUSED_BY {confidence}`, Decision |
| Historian | sonnet (or haiku) | similar_incidents, best_runbook | `SIMILAR_TO`, Decision |
| Responder | haiku | who_to_page, check_policy, actions (page, open GitHub issue, mark rollback) | Decision (APPLIED_POLICY), Events |
| Scribe (on resolve) | sonnet | read timeline | Postmortem, Runbook `RESOLVED {worked}`, success_count++ , Incident.embedding |

Every arrow between agents is a `handoff` call, so the full collaboration is replayable from the graph alone ("show me how the agents handled INC-071" is just a query).

**Real actions** (actions based on the graph): open a GitHub issue in a demo repo with the root-cause path and suspect commit; post the page to a Discord/Slack webhook; "rollback" creates a new `Deploy` with `status:'rolled_back'` linked to the old one. Keep rollback simulated and say so.

## 6. Data source: Kestrel Pay

PagerSage watches a fictional payments company, Kestrel Pay, which lives in `kestrel-pay/` with its own plan: [`kestrel-pay/PLAN.md`](../kestrel-pay/PLAN.md). Kestrel Pay owns its company files, its 90-day history, the four planted patterns and the demo scenarios. PagerSage never generates company data; it **ingests** it, as it would for a real customer.

What PagerSage builds for this (details in `kestrel-pay/PLAN.md` section 4):

- **Seed-time ingest (`make seed`, task G03):** read `kestrel-pay/company/*.yaml` (validated by `pagersage/contracts/seed.py`) and `kestrel-pay/history/export/*.jsonl`, write everything with `MERGE` on stable ids, materialise `IMPACTS`, then run the batch algorithms.
- **Run-time ingest (task B10):** `POST /ingest/deploy` and `POST /ingest/config-change`, next to the Alertmanager-compatible `POST /alerts`. Kestrel Pay's injector (`make inject SCENARIO=pool-exhaustion`) calls these three; it never touches FalkorDB.
- **Live weights:** alerts carry a `health` annotation (0-1) that drives the live-weight trick in section 4.

## 7. (Removed) Homelab OTel traces

Dropped on Oct 8 to keep the setup small. The spare time goes to the MCP server bonus or extra polish instead.

## 8. Demo script (target 3:00)

1. **0:00 Hook (15s).** "It's 2 AM, checkout is erroring. Normally you'd open six dashboards. Watch."
2. **0:15 Company brain (30s).** Canvas shows Kestrel Pay: services coloured by team, size = criticality, red rings = fragility. Ask "who knows the payments DB?" and get the answer with the evidence edges lit.
3. **0:45 Inject (10s).** Run `make inject`. An alert lands on `checkout-api`.
4. **0:55 Agents work (60s).** Timeline panel streams Triage → Investigator → Historian → Responder handoffs. Blast radius pulses out (BFS). Root-cause path lights up: checkout-api → payments-svc → payments-db → config change → commit → person. Decoy deploy is shown and explicitly rejected with its score.
5. **1:55 Memory (30s).** "This looks like INC-042 from last month (and two others). Runbook 'raise pool' worked 3/3." Show vector-only vs graph-reranked results side by side.
6. **2:25 Action (20s).** Discord ping to the on-call owner, GitHub issue opened with the path. Click resolve; Scribe writes the postmortem and the runbook counter becomes 4/4.
7. **2:45 Proof (15s).** FalkorDB Browser: one query replays the whole incident as decisions, evidence and handoffs. "Delete FalkorDB and PagerSage knows nothing." End card: repo URL.

Keep a backup recording in case the live run misbehaves.

## 9. Build order

**Before writing code:**
- Create accounts and keys: Anthropic API, GitHub demo repo for issues, Discord webhook, hosting (VPS/Railway + Vercel). Install Docker; `docker pull falkordb/falkordb`.
- Draft the topology YAML, people/teams list, the 4 planted patterns and the demo storyboard.

**Step 1: Graph first**
- Repo scaffold, Docker Compose (FalkorDB + API), `smoke_algos.py` (section 1 names).
- Schema constraints/indexes (vector + full-text), Kestrel Pay ingest (`make seed`). Kestrel Pay's company files and history are built in parallel (`kestrel-pay/PLAN.md`).
- Batch algorithms (betweenness, pageRank, wcc) writing properties.
- Queries T1-T7 with pytest golden tests against the seeded graph (aim for ~25 tests by the end of step 2).
- **Exit check:** every tool query returns the expected answer for the pool-exhaustion scenario from a Python REPL, no LLM yet.

**Step 2: Agents and memory**
- Claude tool wrappers, orchestrator state machine, handoff/decision writes (T8, T9).
- `/ingest/deploy` and `/ingest/config-change`, Alertmanager-compatible `/alerts` webhook, SSE event stream. Kestrel Pay's injector drives them.
- Scribe: postmortem + runbook success counts + incident embedding (closing the memory loop).
- **Exit check:** `make inject` → resolved incident with full decision trace, from the CLI.

**Step 3: Product surface**
- Next.js UI: canvas graph, path highlighting, agent timeline, incident list, `/ask` box.
- Real actions: Discord webhook, GitHub issue.
- Deploy (FalkorDB + API on one box, frontend on Vercel). Record a backup demo.
- Stretch: FalkorDB-MCPServer bonus ("point Claude Desktop at the same brain").
- **Exit check:** a stranger can open the live URL and trigger the scenario.

**Step 4: Ship**
- README: setup, graph model diagram, every Cypher query with explanation, algorithms used and why, architecture, AI-usage notes.
- Record the demo video. Write a blog post: "Why your incident bot needs a graph, not just a vector DB" (the vector vs graph comparison).
- Polish, fix, and check the deploy is up.

**Cut list if behind (in order):** labelPropagation insight → MCP server → GitHub issue action (keep Discord) → Historian merged into Investigator. Never cut: path highlight, similar-incident memory, decision trace replay.

## 10. Release checklist

- [ ] Public GitHub repo, MIT licence
- [ ] README: one-paragraph pitch, screenshot/GIF, setup (`docker compose up`, `make seed`, `make inject`)
- [ ] README: graph data model (diagram + node/edge tables from section 3)
- [ ] README: every Cypher query and algorithm used, with what it's for
- [ ] README: architecture diagram, agent roles, memory layers mapped to schema
- [ ] README: AI coding assistant usage noted
- [ ] Demo video (≤3-4 min), uploaded, linked
- [ ] Live deployment URL working (and local setup works from a clean clone)
- [ ] Tests passing in CI (GitHub Actions running pytest against a FalkorDB service container)
- [ ] Blog post published and linked
- [ ] No secrets in the repo

## Sources

- Algorithms: https://docs.falkordb.com/algorithms/ (bfs, sppath, sspath, betweenness-centrality, pagerank, wcc, cdlp pages)
- Vector index: https://docs.falkordb.com/cypher/indexing/vector-index.html
- Full-text index: https://docs.falkordb.com/cypher/indexing/fulltext-index.html
- Canvas: https://github.com/FalkorDB/falkordb-canvas
