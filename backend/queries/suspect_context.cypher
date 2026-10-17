// T3 suspect_changes: scoring inputs per suspect service: its fragility, its health, the
// worst health of anything it depends on (directly or not), and the graph's top fragility
// (to normalise). A sick service whose dependencies are sicker is a victim, not a cause.
// Params: $sids (service ids). Returns id, fragility, health, worst_dep_health, max_fragility.
MATCH (all:Service)
WITH max(all.fragility) AS max_fragility
UNWIND $sids AS sid
MATCH (s:Service {id: sid})
OPTIONAL MATCH (s)-[:DEPENDS_ON*1..6]->(dn:Service)
RETURN s.id AS id, coalesce(s.fragility, 0.0) AS fragility, coalesce(s.health, 1.0) AS health,
       min(coalesce(dn.health, 1.0)) AS worst_dep_health, max_fragility
