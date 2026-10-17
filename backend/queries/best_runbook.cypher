// T7 best_runbook: a service's runbooks, best first by smoothed success rate
// (success+1)/(success+fail+2) (procedural memory). An untried runbook scores 0.5, one success out of one
// scores 0.67, so a single lucky run does not beat a proven 3/3.
// Params: $sid, $limit. Returns id, title, steps, success_count, fail_count, success_rate.
MATCH (rb:Runbook)-[:FOR]->(:Service {id: $sid})
WITH rb, (rb.success_count + 1.0) / (rb.success_count + rb.fail_count + 2.0) AS success_rate
RETURN rb.id AS id, rb.title AS title, rb.steps AS steps, rb.success_count AS success_count,
       rb.fail_count AS fail_count, success_rate
ORDER BY success_rate DESC, success_count DESC, id
LIMIT $limit
