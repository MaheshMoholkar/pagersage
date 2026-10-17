// B03 GET /incidents/{id}: one incident's own fields and its shared agent state.
// Params: $iid. Returns the same columns as incidents_list plus summary, state (JSON string)
// and postmortem ({title, body, ts} or null; written by the Scribe, A08).
MATCH (i:Incident {id: $iid})
RETURN i.id AS id, i.title AS title, i.severity AS severity, i.status AS status,
       i.opened_at AS opened_at, i.resolved_at AS resolved_at,
       head([(i)-[:ASSIGNED_TO]->(x) | coalesce(x.name, x.handle)]) AS assigned_to,
       size([(a:Alert)-[:PART_OF]->(i) | a]) AS alerts,
       [(i)-[:AFFECTED]->(s:Service) | s.id] AS services,
       i.summary AS summary, i.state AS state,
       head([(pm:Postmortem)-[:ABOUT]->(i) | {title: pm.title, body: pm.body, ts: pm.ts}])
         AS postmortem
