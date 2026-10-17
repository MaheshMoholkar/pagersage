// Seed (G03): DEPENDS_ON (a calls b) and its materialised reverse IMPACTS (b hurts a).
// IMPACTS exists because algo.bfs has no direction argument; blast_radius walks it.
// Params: $rows = [{from, to, props}]; props = {calls_per_min, p99_ms, weight}.
UNWIND $rows AS r
MATCH (a:Service {id: r.from}), (b:Service {id: r.to})
MERGE (a)-[d:DEPENDS_ON]->(b)
SET d += r.props
MERGE (b)-[:IMPACTS]->(a)
