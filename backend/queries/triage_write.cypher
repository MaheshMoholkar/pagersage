// A04 set_triage: the incident's title, severity and summary, status investigating, the
// embedding similar_incidents searches from (T6), and AFFECTED edges to the impacted services.
// SET runs before UNWIND, so the incident is updated even if $sids were empty.
// Params: $iid, $title, $severity, $summary, $embedding (384 floats), $sids.
MATCH (i:Incident {id: $iid})
SET i.title = $title, i.severity = $severity, i.summary = $summary,
    i.status = 'investigating', i.embedding = vecf32($embedding)
WITH i
UNWIND $sids AS sid
MATCH (s:Service {id: sid})
MERGE (i)-[:AFFECTED]->(s)
