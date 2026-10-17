// B06 /graph: DEPENDS_ON links between the services on screen, with live weight and traffic.
// Params: $ids (service ids, or null for all). Returns source, target, weight, calls_per_min.
MATCH (a:Service)-[d:DEPENDS_ON]->(b:Service)
WHERE $ids IS NULL OR (a.id IN $ids AND b.id IN $ids)
RETURN a.id AS source, b.id AS target, d.weight AS weight, d.calls_per_min AS calls_per_min
ORDER BY source, target
