// Input check for record_decision: which of these policy ids exist?
// Params: $ids. Returns id.
MATCH (p:Policy)
WHERE p.id IN $ids
RETURN p.id AS id
