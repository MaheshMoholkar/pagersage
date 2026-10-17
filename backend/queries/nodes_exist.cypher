// Input check for write tools that link to arbitrary node ids (decision evidence): which of
// these ids exist? Ids are unique across labels, so this matches without a label (a scan of
// a few thousand nodes).
// Params: $ids. Returns id, found (0 or more).
UNWIND $ids AS nid
OPTIONAL MATCH (n)
WHERE n.id = nid
RETURN nid AS id, count(n) AS found
