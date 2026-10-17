// B03/B06: an incident's alerts, oldest first, with the service each fired on.
// Params: $iid. Returns id, service_id, signal, value, threshold, severity, ts.
MATCH (a:Alert)-[:PART_OF]->(:Incident {id: $iid})
MATCH (a)-[:FIRED_ON]->(s:Service)
RETURN a.id AS id, s.id AS service_id, a.signal AS signal, a.value AS value,
       a.threshold AS threshold, a.severity AS severity, a.ts AS ts
ORDER BY ts, id
