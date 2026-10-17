// T3 suspect_changes: deploys and config changes since $since on the alerting service and on
// everything it depends on (the root cause is usually downstream of the symptom).
// Four branches: deploys here, deploys downstream, config changes here, config changes
// downstream. "Here" is its own branch because SSpaths yields nothing for a service with no
// outgoing DEPENDS_ON. pathCount caps the TOTAL paths, so keep 1000 and take the cheapest
// path (dist, in live weight) and the fewest hops per service. Ranking happens in Python.
// Params: $sid, $since. Returns change_id, change_type ('deploy'|'config'), svc_id, ts,
// dist, hops, commits [{sha, message, author}] (an all-null entry when a deploy has none).
MATCH (svc:Service {id: $sid})<-[:TARGETED]-(d:Deploy)
WHERE d.ts >= $since
OPTIONAL MATCH (d)-[:CONTAINS]->(c:Commit)
OPTIONAL MATCH (c)<-[:AUTHORED]-(p:Person)
RETURN d.id AS change_id, 'deploy' AS change_type, svc.id AS svc_id, d.ts AS ts,
       0 AS dist, 0 AS hops, collect({sha: c.sha, message: c.message, author: p.handle}) AS commits
UNION
MATCH (s:Service {id: $sid})
CALL algo.SSpaths({sourceNode: s, relTypes: ['DEPENDS_ON'], relDirection: 'outgoing',
                   weightProp: 'weight', maxLen: 4, pathCount: 1000})
YIELD path, pathWeight
WITH s, last(nodes(path)) AS svc, min(pathWeight) AS dist, min(length(path)) AS hops
WHERE svc <> s
MATCH (svc)<-[:TARGETED]-(d:Deploy)
WHERE d.ts >= $since
OPTIONAL MATCH (d)-[:CONTAINS]->(c:Commit)
OPTIONAL MATCH (c)<-[:AUTHORED]-(p:Person)
RETURN d.id AS change_id, 'deploy' AS change_type, svc.id AS svc_id, d.ts AS ts,
       toInteger(dist) AS dist, hops,
       collect({sha: c.sha, message: c.message, author: p.handle}) AS commits
UNION
MATCH (svc:Service {id: $sid})<-[:CHANGED]-(cfg:ConfigChange)
WHERE cfg.ts >= $since
RETURN cfg.id AS change_id, 'config' AS change_type, svc.id AS svc_id, cfg.ts AS ts,
       0 AS dist, 0 AS hops, [] AS commits
UNION
MATCH (s:Service {id: $sid})
CALL algo.SSpaths({sourceNode: s, relTypes: ['DEPENDS_ON'], relDirection: 'outgoing',
                   weightProp: 'weight', maxLen: 4, pathCount: 1000})
YIELD path, pathWeight
WITH s, last(nodes(path)) AS svc, min(pathWeight) AS dist, min(length(path)) AS hops
WHERE svc <> s
MATCH (svc)<-[:CHANGED]-(cfg:ConfigChange)
WHERE cfg.ts >= $since
RETURN cfg.id AS change_id, 'config' AS change_type, svc.id AS svc_id, cfg.ts AS ts,
       toInteger(dist) AS dist, hops, [] AS commits
