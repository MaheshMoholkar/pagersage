// On call now (top bar): each team's on-call person at $now and when their shift ends.
// Params: $now. Returns team, handle, name, until; one row per team with a shift at $now.
MATCH (p:Person)-[oc:ON_CALL]->(t:Team)
WHERE oc.from <= $now AND oc.to > $now
RETURN t.name AS team, p.handle AS handle, p.name AS name, oc.to AS until
ORDER BY team
