// T2 blast_radius: who is hurt if this service is down = everything that calls it, directly
// or through other services. algo.bfs has no direction argument, so it walks IMPACTS (the
// reverse of DEPENDS_ON, written by the seed loader). BFS leaves out the start node.
// Params: $sid (service id), $max_depth. Returns id, name, tier, team (owning team's name),
// most critical first: by tier, then pageRank criticality.
MATCH (s:Service {id: $sid})
CALL algo.bfs(s, $max_depth, 'IMPACTS') YIELD nodes
UNWIND nodes AS n
OPTIONAL MATCH (t:Team)-[:OWNS]->(n)
RETURN n.id AS id, n.name AS name, n.tier AS tier, t.name AS team
ORDER BY tier, n.criticality DESC, id
