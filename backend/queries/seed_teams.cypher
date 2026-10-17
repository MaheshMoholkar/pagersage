// Seed (G03): Team nodes and OWNS edges from org.yaml.
// Params: $rows = [{props, owns: [service id]}]; props = {id, name, slack_channel}.
UNWIND $rows AS r
MERGE (t:Team {id: r.props.id})
SET t += r.props
WITH t, r
UNWIND r.owns AS sid
MATCH (s:Service {id: sid})
MERGE (t)-[:OWNS]->(s)
