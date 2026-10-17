// Seed (G03): Event nodes (incident timeline, episodic memory) and PART_OF edges.
// Params: $rows = [{props}]; props = AgentEvent.to_node_props() (agent null for past incidents).
UNWIND $rows AS r
MATCH (i:Incident {id: r.props.incident_id})
MERGE (e:Event {id: r.props.id})
SET e += r.props
MERGE (e)-[:PART_OF]->(i)
