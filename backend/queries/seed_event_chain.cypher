// Seed (G03): NEXT edges chaining each incident's events in order.
// Params: $rows = [{from, to}] (event ids, consecutive seq).
UNWIND $rows AS r
MATCH (a:Event {id: r.from}), (b:Event {id: r.to})
MERGE (a)-[:NEXT]->(b)
