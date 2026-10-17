// A05 record_cause: the incident CAUSED_BY {confidence, ts} the change behind it, a Deploy or
// a ConfigChange. Recording the same change again updates its confidence. Two labelled
// OPTIONAL MATCHes keep both lookups on the id index (as in seed_caused_by).
// Params: $iid, $cid, $confidence, $now.
MATCH (i:Incident {id: $iid})
OPTIONAL MATCH (d:Deploy {id: $cid})
OPTIONAL MATCH (c:ConfigChange {id: $cid})
WITH i, coalesce(d, c) AS change
MERGE (i)-[cb:CAUSED_BY]->(change)
SET cb.confidence = $confidence, cb.ts = $now
