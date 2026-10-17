// T10 who_knows: "Who knows the payments DB?" Every person with any tie to the service:
// commits shipped to it, incidents on it they resolved, postmortems they wrote about those
// incidents, and membership of the owning team. The tool weights and ranks the counts.
// Params: $sid. Returns handle, name, commits, incidents_resolved, postmortems_written,
// team_member (0 or 1).
MATCH (s:Service {id: $sid}), (p:Person)
OPTIONAL MATCH (p)-[:AUTHORED]->(c:Commit)<-[:CONTAINS]-(:Deploy)-[:TARGETED]->(s)
WITH s, p, count(DISTINCT c) AS commits
OPTIONAL MATCH (p)-[:RESOLVED]->(i:Incident)-[:AFFECTED]->(s)
WITH s, p, commits, count(DISTINCT i) AS incidents_resolved
OPTIONAL MATCH (p)-[:WROTE]->(:Postmortem)-[:ABOUT]->(j:Incident)-[:AFFECTED]->(s)
WITH s, p, commits, incidents_resolved, count(DISTINCT j) AS postmortems_written
OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)-[:OWNS]->(s)
WITH p, commits, incidents_resolved, postmortems_written, count(t) AS team_member
WHERE commits + incidents_resolved + postmortems_written + team_member > 0
RETURN p.handle AS handle, p.name AS name, commits, incidents_resolved, postmortems_written,
       team_member
