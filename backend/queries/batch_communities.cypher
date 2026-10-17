// Batch (G18): Person.community = labelPropagation over COLLABORATES, the teams people really
// work in, to show next to the org chart (MEMBER_OF). Someone who ships with nobody often
// enough is a community of one.
// Params: none. Returns nothing.
CALL algo.labelPropagation({nodeLabels: ['Person'], relationshipTypes: ['COLLABORATES'],
                            maxIterations: 20})
YIELD node, communityId
SET node.community = communityId
