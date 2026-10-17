// T8b record_decision: BASED_ON each evidence node (any id: service, deploy, config change,
// commit sha, incident, runbook...). The tool skips this call when there is no evidence.
// Params: $did, $evidence (ids, checked to exist first).
MATCH (d:Decision {id: $did})
UNWIND $evidence AS eid
MATCH (e)
WHERE e.id = eid
MERGE (d)-[:BASED_ON]->(e)
