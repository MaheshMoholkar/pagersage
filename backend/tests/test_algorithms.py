"""Batch algorithms (G05): fragility (betweenness), criticality (pageRank), ownership gaps (wcc)."""

import pytest

from pagersage import algorithms, seed


@pytest.fixture
def seeded(graph):
    seed.seed_graph(graph)  # runs the batch algorithms too
    return graph


def _scores(graph, prop):
    rows = graph.ro_query(f"MATCH (s:Service) RETURN s.id, s.{prop}").result_set
    return dict(rows)


def test_kafka_is_most_fragile(seeded):
    ranked = sorted(_scores(seeded, "fragility").items(), key=lambda kv: -kv[1])

    assert ranked[0][0] == "svc:kafka"
    assert ranked[0][1] > 1.5 * ranked[1][1], ranked[:3]  # Kestrel Pay's planted pattern 3


def test_every_service_gets_both_scores(seeded):
    for prop in ("fragility", "criticality"):
        scores = _scores(seeded, prop)
        assert all(isinstance(v, float) for v in scores.values()), (prop, scores)
    assert max(_scores(seeded, "criticality").values()) > 0


def test_running_again_gives_the_same_scores(seeded):
    before = (_scores(seeded, "fragility"), _scores(seeded, "criticality"))

    algorithms.run_batch(seeded)

    assert (_scores(seeded, "fragility"), _scores(seeded, "criticality")) == before


def test_kestrel_pay_has_no_ownership_gaps(seeded):
    assert algorithms.ownership_gaps(seeded) == []


def test_unowned_services_are_gaps_even_when_they_have_dependencies(seeded):
    # A DEPENDS_ON edge ties the new service into the owned part of the graph; it is still a gap.
    seeded.query(
        "MATCH (p:Service {id:'svc:payments-svc'}) "
        "CREATE (:Service {id:'svc:shadow-cron'})-[:DEPENDS_ON]->(p), (:Service {id:'svc:zombie'})"
    )

    assert algorithms.ownership_gaps(seeded) == ["svc:shadow-cron", "svc:zombie"]
