// B09 rollback (simulated): mark the bad deploy rolled_back, as Kestrel Pay's history does for
// deploys that were undone, and record the rollback as a new Deploy of the previous version,
// (new)-[:ROLLED_BACK]->(old). Nothing outside the graph changes.
// Params: $old, $sid, $new, $version, $now.
MATCH (old:Deploy {id: $old})-[:TARGETED]->(s:Service {id: $sid})
SET old.status = 'rolled_back'
CREATE (new:Deploy {id: $new, version: $version, ts: $now, status: 'ok', env: old.env,
                    simulated: true})
CREATE (new)-[:TARGETED]->(s), (new)-[:ROLLED_BACK]->(old)
