// B07/B08 actions: what a page or an issue says about an incident, and who is being paged.
// Params: $iid, $pid (person id, or null). Returns title, severity, services (alerting service
// names), person_name, person_tz (null when $pid is null or unknown). No row: no incident.
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (p:Person {id: $pid})
RETURN i.title AS title, i.severity AS severity,
       [(i)<-[:PART_OF]-(:Alert)-[:FIRED_ON]->(s:Service) | s.name] AS services,
       p.name AS person_name, p.timezone AS person_tz
