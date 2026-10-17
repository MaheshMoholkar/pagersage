// Seed (G03): Commit nodes (id = sha) and AUTHORED edges from commits.jsonl.
// Params: $rows = [{author, props}];
//   props = {id, sha, message, ts, files_changed, lines_changed}.
UNWIND $rows AS r
MATCH (p:Person {id: r.author})
MERGE (c:Commit {id: r.props.id})
SET c += r.props
MERGE (p)-[:AUTHORED]->(c)
