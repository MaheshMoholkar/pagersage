// G17 replay_incident: the whole decision trace of an incident in one query, for the agents
// (Scribe) and for the demo's proof beat in FalkorDB Browser. Every decision with who made
// it, its evidence, precedents and policies; every handoff; how many timeline events.
// Pattern comprehensions bind no relationship variables (FalkorDB 6.0.2 bug, contracts.md).
// Params: $iid. Returns id, title, status, decisions [{id, agent, what, why, confidence, ts,
// evidence, precedents, policies}], handoffs [{id, ts, from, to, note}], event_count.
// No row when the incident does not exist. The tool orders decisions and handoffs.
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (d:Decision)-[:ABOUT]->(i)
OPTIONAL MATCH (d)-[:MADE_BY]->(by)
WITH i, collect(CASE WHEN d IS NULL THEN null ELSE {
       id: d.id, agent: coalesce(by.name, by.handle), what: d.what, why: d.why,
       confidence: d.confidence, ts: d.ts,
       evidence: [(d)-[:BASED_ON]->(e) | e.id],
       precedents: [(p:Decision)-[:PRECEDENT_FOR]->(d) | p.id],
       policies: [(d)-[:APPLIED_POLICY]->(pol:Policy) | pol.id]} END) AS decisions
OPTIONAL MATCH (h:Handoff)-[:ON]->(i)
OPTIONAL MATCH (h)-[:FROM]->(fa:Agent)
OPTIONAL MATCH (h)-[:TO]->(ta:Agent)
WITH i, decisions, collect(CASE WHEN h IS NULL THEN null ELSE {
       id: h.id, ts: h.ts, from: fa.name, to: ta.name, note: h.note} END) AS handoffs
RETURN i.id AS id, i.title AS title, i.status AS status, decisions, handoffs,
       size([(e:Event)-[:PART_OF]->(i) | e]) AS event_count
