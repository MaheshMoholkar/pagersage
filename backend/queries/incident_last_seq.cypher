// Timeline append: the incident's highest Event seq, so the next event is seq + 1 and NEXT
// links from it. No row when the incident does not exist.
// Params: $iid. Returns last_seq (null when the timeline is empty).
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (e:Event)-[:PART_OF]->(i)
RETURN i.id AS iid, max(e.seq) AS last_seq
