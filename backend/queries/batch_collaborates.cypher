// Batch (G18): COLLABORATES {deploys} between two people whose commits shipped in the same
// deploy at least $min_deploys times. One edge per pair (lower id -> higher id). The
// threshold matters: a few one-off cross-team deploys otherwise join everyone into one group.
// Params: $min_deploys. Returns nothing. MERGE + SET, so re-running only updates counts.
MATCH (a:Person)-[:AUTHORED]->(:Commit)<-[:CONTAINS]-(d:Deploy)-[:CONTAINS]->(:Commit)<-[:AUTHORED]-(b:Person)
WHERE a.id < b.id
WITH a, b, count(DISTINCT d) AS deploys
WHERE deploys >= $min_deploys
MERGE (a)-[c:COLLABORATES]->(b)
SET c.deploys = deploys
