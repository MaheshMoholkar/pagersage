// T9 handoff: the Handoff, its timeline Event, the merged state and the new assignment, in
// one statement so it lands whole or not at all.
// Writes the Handoff (FROM, TO, ON), appends a handoff Event to the timeline (PART_OF, NEXT
// from the previous last event), replaces Incident.state with the merged JSON, and moves
// ASSIGNED_TO to the receiving agent. Agent nodes are created on first use.
// Params: $iid, $hid, $now, $note, $state, $event (Event props), $prev_event (id or null),
// $from_id, $from, $from_model, $to_id, $to, $to_model.
MATCH (i:Incident {id: $iid})
MERGE (fa:Agent {id: $from_id})
ON CREATE SET fa.name = $from, fa.model = $from_model
MERGE (ta:Agent {id: $to_id})
ON CREATE SET ta.name = $to, ta.model = $to_model
CREATE (h:Handoff {id: $hid, ts: $now, note: $note})
CREATE (h)-[:FROM]->(fa), (h)-[:TO]->(ta), (h)-[:ON]->(i)
CREATE (e:Event)
SET e += $event, i.state = $state
CREATE (e)-[:PART_OF]->(i)
WITH i, ta, e
OPTIONAL MATCH (prev:Event {id: $prev_event})
FOREACH (p IN CASE WHEN prev IS NULL THEN [] ELSE [prev] END | CREATE (p)-[:NEXT]->(e))
WITH i, ta
OPTIONAL MATCH (i)-[old:ASSIGNED_TO]->()
DELETE old
WITH DISTINCT i, ta
CREATE (i)-[:ASSIGNED_TO]->(ta)
