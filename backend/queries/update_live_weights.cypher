// Live weights (G09): record a service's health from an alert and reprice the edges into it.
// weight = clip(round(100 * health), 5, 100), computed by tools.live_weight: a sick service is
// cheap to walk into, so weighted shortest paths (root_cause_path) run through it.
// Params: $sid, $health (0-1), $weight (int). Returns nothing. If nothing calls the service,
// the second MATCH finds no rows but the health is already set.
MATCH (s:Service {id: $sid})
SET s.health = $health
WITH s
MATCH ()-[d:DEPENDS_ON]->(s)
SET d.weight = $weight
