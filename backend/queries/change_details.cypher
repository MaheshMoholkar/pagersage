// T4 root_cause_path: what a change touched and who is behind it. A deploy brings its commits
// and their authors; a config change brings the person who made it.
// Params: $cid (dep-... or cfg-...). Returns kind ('deploy'|'config'), svc_id,
// links [{sha, person, handle}] (sha null for config changes; all-null when nobody is linked).
MATCH (d:Deploy {id: $cid})-[:TARGETED]->(s:Service)
OPTIONAL MATCH (d)-[:CONTAINS]->(c:Commit)
OPTIONAL MATCH (c)<-[:AUTHORED]-(p:Person)
RETURN 'deploy' AS kind, s.id AS svc_id,
       collect({sha: c.sha, person: p.id, handle: p.handle}) AS links
UNION
MATCH (cfg:ConfigChange {id: $cid})-[:CHANGED]->(s:Service)
OPTIONAL MATCH (p:Person)-[:MADE]->(cfg)
RETURN 'config' AS kind, s.id AS svc_id,
       collect({sha: null, person: p.id, handle: p.handle}) AS links
