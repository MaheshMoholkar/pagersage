// B02 open_or_merge_incident: add an alert to an open incident; the incident's severity rises
// to the alert's when the alert is worse ('sev1' < 'sev2' as strings, and sev1 is worst).
// Params: $iid, $sid, $severity, $alert (Alert props).
MATCH (i:Incident {id: $iid}), (s:Service {id: $sid})
CREATE (a:Alert)
SET a += $alert,
    i.severity = CASE WHEN $severity < i.severity THEN $severity ELSE i.severity END
CREATE (a)-[:FIRED_ON]->(s), (a)-[:PART_OF]->(i)
