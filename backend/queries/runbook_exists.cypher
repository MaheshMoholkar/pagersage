// Input check for record_runbook_outcome: does the runbook exist?
// Params: $rb. Returns id (no row when it does not).
MATCH (rb:Runbook {id: $rb})
RETURN rb.id AS id
