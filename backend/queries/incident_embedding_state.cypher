// Input check for similar_incidents: does the incident exist, and has triage embedded it?
// Params: $iid. Returns found (0 or 1), embedded (bool).
MATCH (i:Incident {id: $iid})
RETURN count(i) AS found, i.embedding IS NOT NULL AS embedded
