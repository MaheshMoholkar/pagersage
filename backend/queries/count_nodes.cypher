// How many nodes of each label the graph has (seed checks, make seed output).
// Params: none. Returns label, n.
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS n
