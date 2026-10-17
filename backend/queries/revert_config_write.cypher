// revert_change (U09, simulated): mark the config change rolled_back and record the revert as
// a new ConfigChange setting the key back, (new)-[:ROLLED_BACK]->(old), like a deploy
// rollback (B09). Nothing outside the graph changes.
// Params: $old, $sid, $new, $now.
MATCH (old:ConfigChange {id: $old})-[:CHANGED]->(s:Service {id: $sid})
SET old.status = 'rolled_back'
CREATE (new:ConfigChange {id: $new, key: old.key, old: old.new, new: old.old, ts: $now,
                          simulated: true})
CREATE (new)-[:CHANGED]->(s), (new)-[:ROLLED_BACK]->(old)
