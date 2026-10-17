"""Real teams vs org chart (G18): COLLABORATES from shared deploys, labelPropagation groups."""

from pagersage import algorithms


def _groups(graph):
    return {frozenset(m["handle"] for m in c["members"]) for c in algorithms.real_teams(graph)}


def test_collaborates_links_people_who_ship_together(seeded_graph):
    rows = seeded_graph.ro_query(
        "MATCH (a:Person)-[c:COLLABORATES]->(b:Person) RETURN a.id < b.id, c.deploys"
    ).result_set
    assert rows
    assert all(ordered and n >= algorithms.MIN_SHARED_DEPLOYS for ordered, n in rows)


def test_payments_and_risk_work_as_their_org_chart_says(seeded_graph):
    groups = _groups(seeded_graph)

    assert frozenset({"priya", "tomas", "hana", "oliver", "kwame"}) in groups
    assert frozenset({"chloe", "arjun", "diego", "fatima"}) in groups


def test_platform_and_checkout_really_ship_as_one_team(seeded_graph):
    together = next(g for g in _groups(seeded_graph) if "noor" in g)

    assert {"jin", "noor", "lukas", "dev", "sofia"} <= together  # Platform
    assert {"amara", "ben", "yuki", "leila", "mateo"} <= together  # Checkout


def test_merchant_experience_is_really_two_teams(seeded_graph):
    groups = _groups(seeded_graph)

    assert frozenset({"grace", "kai"}) in groups
    assert frozenset({"omar", "nina", "lucy"}) in groups


def test_every_member_carries_their_org_chart_team(seeded_graph):
    for community in algorithms.real_teams(seeded_graph):
        assert community["members"]
        assert all(m["team"] for m in community["members"])
        assert community["teams"] == sorted({m["team"] for m in community["members"]})
