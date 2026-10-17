// Seed (G04): store each past incident's embedding for similar_incidents (T6).
// Params: $rows = [{id, embedding: [384 floats]}] from embeddings.embed(incident_text(...)).
UNWIND $rows AS r
MATCH (i:Incident {id: r.id})
SET i.embedding = vecf32(r.embedding)
