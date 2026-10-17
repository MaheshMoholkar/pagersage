// revert_change (U09) for a config change: the change, its service, whether it was already
// reverted, and the highest ConfigChange id so far (the revert continues it).
// Params: $cid. Returns svc_id, key, old, new, status ('ok' when unset), last_config_id.
// No row: unknown. coalesce: a null grouping key next to max() crashes FalkorDB 6.0.2.
MATCH (c:ConfigChange {id: $cid})-[:CHANGED]->(s:Service)
MATCH (x:ConfigChange)
RETURN s.id AS svc_id, c.key AS key, c.old AS old, c.new AS new, coalesce(c.status, 'ok') AS status,
       max(x.id) AS last_config_id
