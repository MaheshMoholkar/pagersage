// Seed (G03): ON_CALL {from, to} shifts, one full rotation per team from on_call.start.
// Params: $rows = [{person, team, from, to}] (epoch seconds, `to` exclusive).
UNWIND $rows AS r
MATCH (p:Person {id: r.person}), (t:Team {id: r.team})
MERGE (p)-[oc:ON_CALL {from: r.from}]->(t)
SET oc.to = r.to
