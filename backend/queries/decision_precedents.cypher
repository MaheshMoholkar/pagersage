// T8c record_decision: decisions taken on similar past incidents become precedents. Runs on
// its own so an empty evidence list never skips it. Similar incidents linked later
// (link_similar, A06) back-fill their precedents there.
// Params: $did.
MATCH (d:Decision {id: $did})-[:ABOUT]->(:Incident)-[:SIMILAR_TO]->(:Incident)<-[:ABOUT]-(prev:Decision)
MERGE (prev)-[:PRECEDENT_FOR]->(d)
