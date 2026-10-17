"""T3 suspect_changes (G08): rank recent changes on the alerting service and everything it
depends on, in the pool-exhaustion `scenario` fixture (tests/scenario.py)."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.schema import ChangeType
from pagersage.contracts.tools import ToolError
from tests.scenario import NOW, SINCE


def test_pool_cut_ranks_first_and_the_decoy_lower(scenario):
    ranked = [s.change_id for s in tools.suspect_changes("svc:checkout-api", SINCE)]

    assert ranked == ["cfg-0061", "dep-0417", "dep-0416"]


def test_suspects_carry_distance_commits_and_the_score_breakdown(scenario):
    by_id = {s.change_id: s for s in tools.suspect_changes("svc:checkout-api", SINCE)}

    cfg, decoy, ships = by_id["cfg-0061"], by_id["dep-0417"], by_id["dep-0416"]
    assert (cfg.change_type, cfg.service_id, cfg.commits) == (
        ChangeType.CONFIG,
        "svc:payments-db",
        [],
    )
    assert (decoy.service_id, decoy.dist) == ("svc:checkout-api", 0)
    assert ships.service_id == "svc:payments-svc"
    assert [(c.sha, c.author) for c in ships.commits] == [("aaaa111", "tomas")]
    assert cfg.dist > ships.dist > 0  # two hops vs one, in path weight
    for s in by_id.values():
        assert set(s.score_parts) == {"recency", "distance", "fragility", "anomaly"}
        product = 1.0
        for part in s.score_parts.values():
            product *= part
        assert s.score == pytest.approx(product)


def test_a_victim_has_no_anomaly_of_its_own(scenario):
    by_id = {s.change_id: s for s in tools.suspect_changes("svc:checkout-api", SINCE)}

    # checkout-api is sick (0.4) but payments-db below it is sicker (0.15): it is a victim.
    assert by_id["dep-0417"].score_parts["anomaly"] == pytest.approx(1.0)
    assert by_id["cfg-0061"].score_parts["anomaly"] == pytest.approx(1 + 10 * (1.0 - 0.15))


def test_changes_before_since_are_ignored(scenario):
    assert tools.suspect_changes("svc:checkout-api", NOW) == []


def test_upstream_changes_are_not_suspects(scenario):
    # From payments-db's point of view, checkout-api and payments-svc are callers, not causes.
    assert [s.change_id for s in tools.suspect_changes("svc:payments-db", SINCE)] == ["cfg-0061"]


@pytest.mark.parametrize(("sid", "since"), [("svc:nope", SINCE), ("svc:checkout-api", -1)])
def test_bad_input_is_a_tool_error(scenario, sid, since):
    with pytest.raises(ToolError):
        tools.suspect_changes(sid, since)
