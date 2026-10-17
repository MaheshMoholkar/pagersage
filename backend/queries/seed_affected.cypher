// Seed (G03): Incident AFFECTED Service edges.
// Params: $rows = [{incident, service}].
UNWIND $rows AS r
MATCH (i:Incident {id: r.incident}), (s:Service {id: r.service})
MERGE (i)-[:AFFECTED]->(s)
