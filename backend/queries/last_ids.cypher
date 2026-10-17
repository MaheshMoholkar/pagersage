// B02 open_or_merge_incident: the highest Alert and Incident ids so far; new ones continue
// them (alt-00061, INC-051). Ids are zero-padded, so max() of the strings is the latest.
// Params: none. Returns alert_id, incident_id (null when there are none yet).
OPTIONAL MATCH (a:Alert)
WITH max(a.id) AS alert_id
OPTIONAL MATCH (i:Incident)
RETURN alert_id, max(i.id) AS incident_id
