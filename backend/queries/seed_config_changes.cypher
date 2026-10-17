// Seed (G03): ConfigChange nodes with CHANGED and MADE edges from config_changes.jsonl.
// Params: $rows = [{service, made_by, props}]; props = {id, key, old, new, ts}.
UNWIND $rows AS r
MATCH (s:Service {id: r.service}), (p:Person {id: r.made_by})
MERGE (c:ConfigChange {id: r.props.id})
SET c += r.props
MERGE (c)-[:CHANGED]->(s)
MERGE (p)-[:MADE]->(c)
