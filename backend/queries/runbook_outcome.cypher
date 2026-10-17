// A08 record_runbook_outcome: Runbook RESOLVED {ts, worked} Incident (again: updated), then
// success_count / fail_count recounted from all its RESOLVED edges, as the seed derives them.
// Params: $rb, $iid, $worked, $now. Returns success_count, fail_count.
MATCH (rb:Runbook {id: $rb}), (i:Incident {id: $iid})
MERGE (rb)-[x:RESOLVED]->(i)
SET x.ts = $now, x.worked = $worked
WITH rb
MATCH (rb)-[r:RESOLVED]->(:Incident)
WITH rb, sum(CASE WHEN r.worked THEN 1 ELSE 0 END) AS ok,
     sum(CASE WHEN r.worked THEN 0 ELSE 1 END) AS bad
SET rb.success_count = ok, rb.fail_count = bad
RETURN ok AS success_count, bad AS fail_count
