// Input check for link_similar: which of these ids are incidents?
// Params: $ids. Returns id.
MATCH (i:Incident)
WHERE i.id IN $ids
RETURN i.id AS id
