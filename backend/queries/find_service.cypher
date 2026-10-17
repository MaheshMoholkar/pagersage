// T1 find_service: services whose full-text index (name, description) matches $q, best first.
// $q is a RediSearch query; the tool scopes it to @name, then to @description, so a name
// match outranks a service that only mentions the word in its description.
// Params: $q (e.g. '@name:(%paymnts%)'), $limit. Returns id, name, score.
CALL db.idx.fulltext.queryNodes('Service', $q) YIELD node, score
RETURN node.id AS id, node.name AS name, score
ORDER BY score DESC, id
LIMIT $limit
