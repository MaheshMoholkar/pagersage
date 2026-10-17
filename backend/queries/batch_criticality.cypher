// Batch (G05): Service.criticality = pageRank on DEPENDS_ON. A service many (important)
// services call scores high, so it ranks first in blast radius and sizes nodes on the canvas.
// Params: none. Returns nothing.
CALL algo.pageRank('Service', 'DEPENDS_ON')
YIELD node, score
SET node.criticality = score
