// T8 record_decision: how many decisions an incident already has (the next one is n + 1).
// Also the incident check: no row when the incident does not exist (grouping on i.id, since
// a bare count() returns a row of 0 even then).
// Params: $iid. Returns iid, n.
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (d:Decision)-[:ABOUT]->(i)
RETURN i.id AS iid, count(d) AS n
