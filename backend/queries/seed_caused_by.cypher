// Seed (G03): Incident CAUSED_BY {confidence} a Deploy or a ConfigChange.
// Params: $rows = [{incident, change, confidence}]; change is a dep-/cfg- id.
// Two labelled OPTIONAL MATCHes keep both lookups on the id index.
UNWIND $rows AS r
MATCH (i:Incident {id: r.incident})
OPTIONAL MATCH (d:Deploy {id: r.change})
OPTIONAL MATCH (c:ConfigChange {id: r.change})
WITH i, r, coalesce(d, c) AS change
MERGE (i)-[cb:CAUSED_BY]->(change)
SET cb.confidence = r.confidence
