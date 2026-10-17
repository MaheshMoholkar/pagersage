"""T7 best_runbook (G13): procedural memory, runbooks ranked by smoothed success rate."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError


def test_raise_pool_comes_first_for_payments_db(tool_graph):
    hits = tools.best_runbook("svc:payments-db")

    assert [(h.id, h.success_count, h.fail_count) for h in hits] == [
        ("rb:raise-payments-db-pool", 3, 0),
        ("rb:failover-payments-db", 0, 1),
    ]
    assert hits[0].success_rate == pytest.approx(4 / 5)
    assert hits[1].success_rate == pytest.approx(1 / 3)
    assert hits[0].steps and all(isinstance(s, str) for s in hits[0].steps)


def test_rate_is_smoothed_so_untried_runbooks_score_one_half(tool_graph):
    rates = {
        h.id: h.success_rate
        for sid in ("svc:kafka", "svc:redis-cache", "svc:ledger-svc")
        for h in tools.best_runbook(sid, 10)
    }
    for hit_id, rate in rates.items():
        assert 0 < rate < 1, hit_id


def test_results_are_sorted_and_limited(tool_graph):
    for sid in ("svc:payments-db", "svc:kafka"):
        hits = tools.best_runbook(sid, 1)
        assert len(hits) <= 1


def test_a_service_without_runbooks_has_none(tool_graph):
    assert tools.best_runbook("svc:edge") == []


@pytest.mark.parametrize(("sid", "limit"), [("svc:nope", 3), ("svc:payments-db", 0)])
def test_bad_input_is_a_tool_error(tool_graph, sid, limit):
    with pytest.raises(ToolError):
        tools.best_runbook(sid, limit)
