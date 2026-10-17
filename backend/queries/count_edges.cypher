// How many edges of each relationship type the graph has (seed checks, make seed output).
// Params: none. Returns type, n.
MATCH ()-[e]->()
RETURN type(e) AS type, count(e) AS n
