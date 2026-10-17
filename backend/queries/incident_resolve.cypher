// B09 resolve: close the incident with its summary, and list the services its alerts fired on
// so the caller can mark them healthy again (live weights back to normal).
// Params: $iid, $now, $summary. Returns services (ids).
MATCH (i:Incident {id: $iid})
SET i.status = 'resolved', i.resolved_at = $now, i.summary = $summary
RETURN [(i)<-[:PART_OF]-(:Alert)-[:FIRED_ON]->(s:Service) | s.id] AS services
