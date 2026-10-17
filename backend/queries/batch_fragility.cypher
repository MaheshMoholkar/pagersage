// Batch (G05): Service.fragility = betweenness on DEPENDS_ON. How many dependency paths run
// through a service, so how much breaks if it goes down. Kafka scores highest.
// FalkorDB's betweenness is directed (a pure sink scores 0) and samples source nodes unless
// samplingSize >= the number of services, so the caller passes that count.
// Params: $sampling (int, >= number of Service nodes). Returns nothing.
CALL algo.betweenness({nodeLabels: ['Service'], relationshipTypes: ['DEPENDS_ON'],
                       samplingSize: $sampling, samplingSeed: 42})
YIELD node, score
SET node.fragility = score
