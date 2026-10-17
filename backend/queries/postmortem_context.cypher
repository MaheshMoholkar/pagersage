// A08 write_postmortem input: the incident's status, and the title and summary its embedding
// is refreshed from. No row when the incident does not exist.
// Params: $iid. Returns status, title, summary.
MATCH (i:Incident {id: $iid})
RETURN i.status AS status, i.title AS title, i.summary AS summary
