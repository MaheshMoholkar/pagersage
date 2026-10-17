"""The pool-exhaustion scenario (kestrel-pay/scenarios/pool-exhaustion.yaml) injected by hand,
as B10's /ingest and B02's /alerts will do it: changes, then alert health via the real
live-weight updater. Shared by the suspect_changes and root_cause_path tests."""

NOW = 1_792_500_000  # after Kestrel Pay's history ends, so only the scenario's changes are recent
SINCE = NOW - 3600

# kestrel-pay/scenarios/pool-exhaustion.yaml, `at` seconds relative to the first alert (NOW)
SCENARIO = """
MATCH (tomas:Person {id:'person:tomas'}), (ben:Person {id:'person:ben'}),
      (psvc:Service {id:'svc:payments-svc'}), (pdb:Service {id:'svc:payments-db'}),
      (chk:Service {id:'svc:checkout-api'})
CREATE (pc:Commit {id:'aaaa111', sha:'aaaa111', ts:$now-900, files_changed:1, lines_changed:1,
                   message:'payments-db: lower max_pool_size to 60 to cut idle connections'}),
       (tomas)-[:AUTHORED]->(pc),
       (pd:Deploy {id:'dep-0416', version:'v3.0.0', ts:$now-360, status:'ok', env:'prod'}),
       (pd)-[:TARGETED]->(psvc), (pd)-[:CONTAINS]->(pc), (tomas)-[:DEPLOYED]->(pd),
       (cfg:ConfigChange {id:'cfg-0061', key:'max_pool_size', old:'100', new:'60', ts:$now-360}),
       (cfg)-[:CHANGED]->(pdb), (tomas)-[:MADE]->(cfg),
       (cc:Commit {id:'bbbb222', sha:'bbbb222', ts:$now-300, files_changed:1, lines_changed:4,
                   message:'checkout: add the Apple Pay express button'}),
       (ben)-[:AUTHORED]->(cc),
       (cd:Deploy {id:'dep-0417', version:'v2.40.0', ts:$now-60, status:'ok', env:'prod'}),
       (cd)-[:TARGETED]->(chk), (cd)-[:CONTAINS]->(cc), (ben)-[:DEPLOYED]->(cd)
"""

# alert health from the scenario's two alerts (payments-db saturation, checkout-api errors)
HEALTH = {"svc:payments-db": 0.15, "svc:checkout-api": 0.4}

# The incident the alerts open (B02) after triage writes its text and embedding (A04).
LIVE_INCIDENT = {
    "id": "INC-051",
    "title": "checkout-api errors: payments-db connection pool exhausted",
    "summary": "payments-svc cannot get connections from payments-db; checkout fails.",
}
PATH = ["svc:checkout-api", "svc:payments-svc", "svc:payments-db"]
