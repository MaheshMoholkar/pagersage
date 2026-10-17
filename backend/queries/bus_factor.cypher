// T10 bus_factor: services up to $max_tier where exactly one person authored the commits
// shipped since $since. If they are away, nobody else has touched the code.
// Params: $max_tier, $since. Returns service_id, tier, sole_author (handle), by tier then id.
MATCH (s:Service)<-[:TARGETED]-(d:Deploy)-[:CONTAINS]->(:Commit)<-[:AUTHORED]-(p:Person)
WHERE s.tier <= $max_tier AND d.ts >= $since
WITH s, collect(DISTINCT p.handle) AS authors
WHERE size(authors) = 1
RETURN s.id AS service_id, s.tier AS tier, authors[0] AS sole_author
ORDER BY tier, service_id
