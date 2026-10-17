// T4 root_cause_path: the cheapest DEPENDS_ON path from the alerting service to the suspect's
// service, in live weight (G09: edges into sick services are cheap, so the path runs through
// the sick part of the system). This is the path the canvas highlights.
// Params: $alerting, $suspect (service ids). Returns services (ids, in order), path_weight.
// No row when the suspect is not downstream of the alerting service.
MATCH (a:Service {id: $alerting}), (b:Service {id: $suspect})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['DEPENDS_ON'],
                   relDirection: 'outgoing', weightProp: 'weight', pathCount: 1})
YIELD path, pathWeight
RETURN [n IN nodes(path) | n.id] AS services, toInteger(pathWeight) AS path_weight
