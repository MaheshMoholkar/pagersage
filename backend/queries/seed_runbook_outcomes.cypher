// Seed (G03): Runbook RESOLVED {ts, worked} Incident: procedural memory from past incidents.
// Params: $rows = [{runbook, incident, ts, worked}].
UNWIND $rows AS r
MATCH (rb:Runbook {id: r.runbook}), (i:Incident {id: r.incident})
MERGE (rb)-[x:RESOLVED {ts: r.ts}]->(i)
SET x.worked = r.worked
