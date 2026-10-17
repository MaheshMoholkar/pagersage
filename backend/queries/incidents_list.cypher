// B03 GET /incidents: the incident feed, newest first, optionally one status only.
// Comprehensions bind no relationship variables (FalkorDB 6.0.2 bug, see contracts.md).
// Params: $status (or null for all), $limit. Returns id, title, severity, status, opened_at,
// resolved_at, assigned_to (agent name or person handle), alerts (count), services (ids).
MATCH (i:Incident)
WHERE $status IS NULL OR i.status = $status
RETURN i.id AS id, i.title AS title, i.severity AS severity, i.status AS status,
       i.opened_at AS opened_at, i.resolved_at AS resolved_at,
       head([(i)-[:ASSIGNED_TO]->(x) | coalesce(x.name, x.handle)]) AS assigned_to,
       size([(a:Alert)-[:PART_OF]->(i) | a]) AS alerts,
       [(i)-[:AFFECTED]->(s:Service) | s.id] AS services
ORDER BY opened_at DESC, id DESC
LIMIT $limit
