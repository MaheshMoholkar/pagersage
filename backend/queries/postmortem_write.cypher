// A08 write_postmortem: the incident's Postmortem (pm:<incident>, ABOUT it), WROTE by the
// Scribe agent (created on first use), and the incident embedding refreshed from its final
// title and summary so the next similar_incidents finds it. Writing again replaces the text.
// Params: $iid, $pid, $title, $body, $now, $agent_id, $agent, $model, $embedding.
MATCH (i:Incident {id: $iid})
MERGE (a:Agent {id: $agent_id})
ON CREATE SET a.name = $agent, a.model = $model
MERGE (pm:Postmortem {id: $pid})
SET pm.title = $title, pm.body = $body, pm.ts = $now, i.embedding = vecf32($embedding)
MERGE (pm)-[:ABOUT]->(i)
MERGE (a)-[:WROTE]->(pm)
