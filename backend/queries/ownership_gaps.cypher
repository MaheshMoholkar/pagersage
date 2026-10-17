// Batch (G05): services no team owns. Weakly connected components over OWNS only: a component
// without a Team is unowned. (Over DEPENDS_ON too, nearly everything joins one big component
// that has a team, which would hide an unowned service.)
// Params: none. Returns id of each unowned service, sorted.
CALL algo.wcc({nodeLabels: ['Service', 'Team'], relationshipTypes: ['OWNS']})
YIELD node, componentId
WITH componentId, collect(node) AS members
WHERE none(m IN members WHERE m:Team)
UNWIND members AS s
RETURN s.id AS id
ORDER BY id
