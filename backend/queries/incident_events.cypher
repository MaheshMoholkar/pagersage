// B03/B04: an incident's timeline events after $after_seq, in order (the SSE stream replays
// from Last-Event-ID with this).
// Params: $iid, $after_seq (0 for all). Returns props (Event node properties).
MATCH (e:Event)-[:PART_OF]->(:Incident {id: $iid})
WHERE e.seq > $after_seq
RETURN properties(e) AS props
ORDER BY e.seq
