// A06 link_similar: decisions already made on this incident (the Investigator's) get
// PRECEDENT_FOR from every decision made on the similar incident. Decisions recorded later
// get theirs in record_decision (decision_precedents).
// Params: $iid, $other.
MATCH (d:Decision)-[:ABOUT]->(:Incident {id: $iid})
MATCH (prev:Decision)-[:ABOUT]->(:Incident {id: $other})
MERGE (prev)-[:PRECEDENT_FOR]->(d)
