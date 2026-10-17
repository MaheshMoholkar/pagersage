// Seed (G03): Policy nodes from policies.yaml.
// Params: $rows = [{props}]; props = {id, name, rule, actions, max_tier}.
UNWIND $rows AS r
MERGE (p:Policy {id: r.props.id})
SET p += r.props
