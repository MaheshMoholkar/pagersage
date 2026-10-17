// Timeline append: one Event on an incident's timeline (episodic memory), PART_OF the incident
// and chained with NEXT from the previous last event. Used for system events such as alerts;
// agent events go through the A11 emitter, handoffs through handoff_write.
// Params: $iid, $event (AgentEvent.to_node_props()), $prev_event (id or null).
MATCH (i:Incident {id: $iid})
CREATE (e:Event)
SET e += $event
CREATE (e)-[:PART_OF]->(i)
WITH e
OPTIONAL MATCH (prev:Event {id: $prev_event})
FOREACH (p IN CASE WHEN prev IS NULL THEN [] ELSE [prev] END | CREATE (p)-[:NEXT]->(e))
