// G18 real teams vs org chart: each labelPropagation community with its members and the
// org-chart team of each member, largest first.
// Params: none. Returns community, members [{handle, name, team}].
MATCH (p:Person)-[:MEMBER_OF]->(t:Team)
WITH p.community AS community, collect({handle: p.handle, name: p.name, team: t.name}) AS members
RETURN community, members
ORDER BY size(members) DESC, community
