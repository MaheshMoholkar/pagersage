// B02 open_or_merge_incident: an open incident, opened in the 10 minutes before this alert,
// with an alert on the same service or on one within 3 DEPENDS_ON hops in either direction.
// That keeps a cause and its symptoms in one incident: payments-db saturating and
// checkout-api erroring 20 seconds later are the same failure, two hops apart.
// Params: $sid, $ts, $window (seconds). Returns id of the newest match.
MATCH (svc:Service {id: $sid})
MATCH (i:Incident)<-[:PART_OF]-(:Alert)-[:FIRED_ON]->(other:Service)
WHERE i.status <> 'resolved' AND i.opened_at >= $ts - $window AND i.opened_at <= $ts
  AND (other = svc OR (svc)-[:DEPENDS_ON*1..3]-(other))
RETURN DISTINCT i.id AS id, i.opened_at AS opened_at
ORDER BY opened_at DESC
LIMIT 1
