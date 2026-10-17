// T5 who_to_page: the owning team's on-call at $now, then the people who most recently
// shipped commits to the service (deploys at or before $now), with their own team.
// UNION needs the same column names in both branches. The author branch keeps 3 so the tool
// can drop the on-call person and still page two others; the tool orders the result.
// Params: $sid, $now. Returns handle, team, reason ('on_call'|'recent_author'), ts.
MATCH (:Service {id: $sid})<-[:OWNS]-(t:Team)<-[oc:ON_CALL]-(p:Person)
WHERE oc.from <= $now AND oc.to > $now
RETURN p.handle AS handle, t.name AS team, 'on_call' AS reason, oc.from AS ts
UNION
MATCH (:Service {id: $sid})<-[:TARGETED]-(d:Deploy)-[:CONTAINS]->(:Commit)<-[:AUTHORED]-(p:Person)
WHERE d.ts <= $now
WITH p, max(d.ts) AS ts
ORDER BY ts DESC, p.handle
LIMIT 3
MATCH (p)-[:MEMBER_OF]->(t:Team)
RETURN p.handle AS handle, t.name AS team, 'recent_author' AS reason, ts
