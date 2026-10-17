// Seed (G03): Alert nodes with FIRED_ON and PART_OF edges.
// Params: $rows = [{service, incident, props}];
//   props = {id, ts, signal, value, threshold, severity}.
UNWIND $rows AS r
MATCH (s:Service {id: r.service}), (i:Incident {id: r.incident})
MERGE (a:Alert {id: r.props.id})
SET a += r.props
MERGE (a)-[:FIRED_ON]->(s)
MERGE (a)-[:PART_OF]->(i)
