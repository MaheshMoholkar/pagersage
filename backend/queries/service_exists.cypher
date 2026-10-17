// Input check for tools that take a service id: does it exist?
// Params: $sid. Returns n (0 or 1).
MATCH (s:Service {id: $sid})
RETURN count(s) AS n
