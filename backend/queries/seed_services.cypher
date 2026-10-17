// Seed (G03): Service nodes from topology.yaml.
// Params: $rows = [{props}]; props = {id, name, tier, language, description, health}.
// Returns nothing. MERGE on id, so re-running updates in place.
UNWIND $rows AS r
MERGE (s:Service {id: r.props.id})
SET s += r.props
