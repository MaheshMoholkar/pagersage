// T8a record_decision: the Decision node, ABOUT its incident, MADE_BY the agent. Agent nodes
// are created on first use.
// Params: $did, $iid, $agent_id, $agent (name), $model, $what, $why, $now, $confidence.
MATCH (i:Incident {id: $iid})
MERGE (a:Agent {id: $agent_id})
ON CREATE SET a.name = $agent, a.model = $model
CREATE (d:Decision {id: $did, what: $what, why: $why, ts: $now, confidence: $confidence})
CREATE (d)-[:ABOUT]->(i), (d)-[:MADE_BY]->(a)
