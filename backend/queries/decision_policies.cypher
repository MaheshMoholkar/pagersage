// T8 record_decision: APPLIED_POLICY for each policy the agent checked (check_policy, A10).
// Params: $did, $policies (ids). The tool skips this call when there are none.
MATCH (d:Decision {id: $did})
UNWIND $policies AS pid
MATCH (p:Policy {id: pid})
MERGE (d)-[:APPLIED_POLICY]->(p)
