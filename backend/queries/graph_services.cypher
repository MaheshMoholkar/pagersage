// B06 /graph: services for the canvas, with what it colours and sizes them by: owning team,
// tier, criticality (pageRank), fragility (betweenness) and live health.
// Params: $ids (service ids, or null for every service). Returns id, name, tier, team,
// criticality, fragility, health.
MATCH (s:Service)
WHERE $ids IS NULL OR s.id IN $ids
OPTIONAL MATCH (t:Team)-[:OWNS]->(s)
RETURN s.id AS id, s.name AS name, s.tier AS tier, t.name AS team,
       s.criticality AS criticality, s.fragility AS fragility, s.health AS health
ORDER BY id
