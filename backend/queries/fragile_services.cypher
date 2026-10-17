// T10 fragile_services: services whose failure cuts the most dependency paths, from the
// precomputed betweenness (Service.fragility, G05), with pageRank criticality alongside.
// Params: $limit. Returns id, name, fragility, criticality.
MATCH (s:Service)
RETURN s.id AS id, s.name AS name, s.fragility AS fragility, s.criticality AS criticality
ORDER BY fragility DESC, id
LIMIT $limit
