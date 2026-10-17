// Seed (G03): past Incident nodes and who resolved them, from incidents.jsonl.
// Params: $rows = [{resolved_by, props}];
//   props = {id, title, severity, status, opened_at, resolved_at, summary}.
// The embedding is added later by G04.
UNWIND $rows AS r
MATCH (p:Person {id: r.resolved_by})
MERGE (i:Incident {id: r.props.id})
SET i += r.props
MERGE (p)-[:RESOLVED]->(i)
