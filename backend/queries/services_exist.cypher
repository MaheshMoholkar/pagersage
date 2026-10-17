// Input check for set_triage: which of these ids are services?
// Params: $ids. Returns id.
MATCH (s:Service)
WHERE s.id IN $ids
RETURN s.id AS id
