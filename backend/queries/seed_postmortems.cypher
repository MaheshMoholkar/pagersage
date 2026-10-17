// Seed (G03): Postmortem nodes with ABOUT and WROTE edges.
// Params: $rows = [{incident, author, props}]; props = {id, title, body, ts}.
UNWIND $rows AS r
MATCH (i:Incident {id: r.incident}), (p:Person {id: r.author})
MERGE (pm:Postmortem {id: r.props.id})
SET pm += r.props
MERGE (pm)-[:ABOUT]->(i)
MERGE (p)-[:WROTE]->(pm)
