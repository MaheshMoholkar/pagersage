// T8 check_policy: the policies that apply before an action on a service (A10). A policy
// applies when it lists the action and the service's tier is at most its max_tier (a policy
// without max_tier applies to every tier).
// Params: $action ('page' | 'issue' | 'rollback'), $sid. Returns id, name, rule.
MATCH (s:Service {id: $sid}), (p:Policy)
WHERE $action IN p.actions AND (p.max_tier IS NULL OR s.tier <= p.max_tier)
RETURN p.id AS id, p.name AS name, p.rule AS rule
ORDER BY id
