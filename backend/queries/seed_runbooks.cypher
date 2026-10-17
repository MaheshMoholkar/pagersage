// Seed (G03): Runbook nodes and FOR edges from runbooks.yaml.
// Params: $rows = [{service, props}];
//   props = {id, title, steps, success_count, fail_count} (counts from past incidents).
UNWIND $rows AS r
MATCH (s:Service {id: r.service})
MERGE (rb:Runbook {id: r.props.id})
SET rb += r.props
MERGE (rb)-[:FOR]->(s)
