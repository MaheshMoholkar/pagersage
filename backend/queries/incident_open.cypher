// B02 open_or_merge_incident: open a new incident with its first alert (FIRED_ON, PART_OF).
// Triage (A04) later rewrites the title and adds AFFECTED, summary and the embedding.
// Params: $iid, $title, $severity, $ts, $sid, $alert (Alert props).
MATCH (s:Service {id: $sid})
CREATE (i:Incident {id: $iid, title: $title, severity: $severity, status: 'open',
                    opened_at: $ts, summary: ''})
CREATE (a:Alert)
SET a += $alert
CREATE (a)-[:FIRED_ON]->(s), (a)-[:PART_OF]->(i)
