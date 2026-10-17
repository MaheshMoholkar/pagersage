// B09 rollback: the deploy to undo, its service and status, the version to go back to (the
// newest earlier deploy on that service that was not itself rolled back) and the highest
// Deploy id so far (the rollback deploy continues it).
// Params: $did. Returns svc_id, status, env, previous_version, last_deploy_id. No row: unknown.
MATCH (old:Deploy {id: $did})-[:TARGETED]->(s:Service)
OPTIONAL MATCH (prev:Deploy)-[:TARGETED]->(s)
WHERE prev.ts < old.ts AND prev.status = 'ok'
WITH s, old, prev
ORDER BY prev.ts DESC
WITH s, old, collect(prev.version)[0] AS previous_version
MATCH (d:Deploy)
RETURN s.id AS svc_id, old.status AS status, old.env AS env, previous_version,
       max(d.id) AS last_deploy_id
