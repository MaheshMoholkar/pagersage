// T9 handoff: an incident's shared state, last event seq and handoff count, read before the
// write. No row when the incident does not exist.
// Params: $iid. Returns state (JSON string or null), last_seq (null = no events yet),
// handoffs (count so far).
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (e:Event)-[:PART_OF]->(i)
WITH i, max(e.seq) AS last_seq
OPTIONAL MATCH (h:Handoff)-[:ON]->(i)
RETURN i.state AS state, last_seq, count(h) AS handoffs
