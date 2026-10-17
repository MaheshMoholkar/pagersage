// Seed (G03): Person nodes and MEMBER_OF edges from org.yaml.
// Params: $rows = [{team, props}]; props = {id, name, handle, timezone, role}.
UNWIND $rows AS r
MATCH (t:Team {id: r.team})
MERGE (p:Person {id: r.props.id})
SET p += r.props
MERGE (p)-[:MEMBER_OF]->(t)
