// Input check: an incident's status. No row when the incident does not exist.
// Params: $iid. Returns status.
MATCH (i:Incident {id: $iid})
RETURN i.status AS status
