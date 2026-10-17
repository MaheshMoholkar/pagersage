// T6 similar_incidents: past incidents nearest to this one by text, from vector search over
// its own embedding (written at triage); the tool then ranks them with what the graph knows
// about each one ("has this happened before?").
// score from the index is cosine distance, so similarity is 1 - score.
// FalkorDB 6.0.2: a pattern comprehension that binds a relationship variable breaks the
// comprehensions after it, so runbook outcomes (r.worked) come from OPTIONAL MATCH + collect.
// Params: $iid (current incident), $k (candidates + 1, the incident finds itself).
// Returns id, title, sim, opened_at, affected [service id], cause_services [service id],
// postmortems [title], runbooks [{id, title, success_count, worked}] (all-null when none).
MATCH (cur:Incident {id: $iid})
CALL db.idx.vector.queryNodes('Incident', 'embedding', $k, cur.embedding) YIELD node AS i, score
WITH cur, i, score
WHERE i <> cur
OPTIONAL MATCH (rb:Runbook)-[r:RESOLVED]->(i)
WITH i, score,
     collect({id: rb.id, title: rb.title, success_count: rb.success_count, worked: r.worked})
       AS runbooks
RETURN i.id AS id, i.title AS title, 1 - score AS sim, i.opened_at AS opened_at,
       [(i)-[:AFFECTED]->(s:Service) | s.id] AS affected,
       [(i)-[:CAUSED_BY]->()-[:CHANGED|TARGETED]->(s:Service) | s.id] AS cause_services,
       [(pm:Postmortem)-[:ABOUT]->(i) | pm.title] AS postmortems,
       runbooks
