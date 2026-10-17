// U06/U07 investigation view: what the UI needs to rerun the Investigator's and Historian's
// reads for one incident. No row when the incident does not exist.
// Params: $iid. Returns state (JSON), alerting (service ids), first_alert (ts),
// causes (CAUSED_BY ids, most confident first), affected (AFFECTED service ids).
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (a:Alert)-[:PART_OF]->(i)
OPTIONAL MATCH (a)-[:FIRED_ON]->(s:Service)
WITH i, collect(DISTINCT s.id) AS alerting, min(a.ts) AS first_alert
OPTIONAL MATCH (i)-[c:CAUSED_BY]->(x)
WITH i, alerting, first_alert, x, c
ORDER BY c.confidence DESC
WITH i, alerting, first_alert, collect(x.id) AS causes
OPTIONAL MATCH (i)-[:AFFECTED]->(f:Service)
RETURN i.state AS state, alerting, first_alert, causes, collect(f.id) AS affected
