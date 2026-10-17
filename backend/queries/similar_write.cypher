// A06 link_similar: this incident is SIMILAR_TO {score} a past incident (Historian). Linking
// again updates the score.
// Params: $iid, $other, $score.
MATCH (i:Incident {id: $iid}), (o:Incident {id: $other})
MERGE (i)-[s:SIMILAR_TO]->(o)
SET s.score = $score
