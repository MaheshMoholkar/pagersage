// B06 /graph?incident=: the services an incident is about (alerting and AFFECTED) plus their
// direct DEPENDS_ON neighbours, so the canvas shows the incident in its context.
// Params: $iid. Returns id. No rows when the incident has no services yet.
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (i)<-[:PART_OF]-(:Alert)-[:FIRED_ON]->(a:Service)
OPTIONAL MATCH (i)-[:AFFECTED]->(b:Service)
WITH collect(DISTINCT a) + collect(DISTINCT b) AS core
UNWIND core AS s
OPTIONAL MATCH (s)-[:DEPENDS_ON]-(n:Service)
WITH collect(DISTINCT s.id) + collect(DISTINCT n.id) AS ids
UNWIND ids AS id
RETURN DISTINCT id
ORDER BY id
