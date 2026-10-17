// Seed (G03): Deploy nodes with TARGETED, DEPLOYED and CONTAINS edges from deploys.jsonl.
// Params: $rows = [{service, deployed_by, commits: [sha], props}];
//   props = {id, version, ts, status, env}. Commits must be seeded first.
UNWIND $rows AS r
MATCH (s:Service {id: r.service}), (p:Person {id: r.deployed_by})
MERGE (d:Deploy {id: r.props.id})
SET d += r.props
MERGE (d)-[:TARGETED]->(s)
MERGE (p)-[:DEPLOYED]->(d)
WITH d, r
UNWIND r.commits AS sha
MATCH (c:Commit {id: sha})
MERGE (d)-[:CONTAINS]->(c)
