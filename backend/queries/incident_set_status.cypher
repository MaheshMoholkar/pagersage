// Orchestrator (A03): set an incident's status, e.g. needs_human when an agent cannot finish.
// Params: $iid, $status.
MATCH (i:Incident {id: $iid})
SET i.status = $status
