// B06 /graph: any nodes by id (deploys, commits, people... named in highlights), with their
// label and a display name. Ids are unique across labels, so this matches without a label.
// Params: $ids. Returns id, kind (label), name.
UNWIND $ids AS nid
MATCH (n)
WHERE n.id = nid
RETURN n.id AS id, labels(n)[0] AS kind,
       coalesce(n.name, n.title, n.handle, n.version, n.key, n.message, n.id) AS name
