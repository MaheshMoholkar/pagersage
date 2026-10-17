"""T10 company-brain tools (G16): who knows a service, bus factor, fragile services."""

from datetime import UTC, datetime

import pytest

from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError

DEMO_WEEK = int(datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp())


@pytest.fixture
def brain(tool_graph, monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: DEMO_WEEK)
    return tool_graph


def test_priya_knows_the_payments_db_best(brain):
    experts = tools.who_knows("svc:payments-db")

    top = experts[0]
    assert top.handle == "priya" and top.name
    assert top.reasons == {
        "commits": 11,
        "incidents_resolved": 2,
        "postmortems_written": 2,
        "team_member": 1,
    }
    w = tools.EXPERT_WEIGHTS
    assert top.score == sum(w[k] * v for k, v in top.reasons.items())
    scores = [e.score for e in experts]
    assert scores == sorted(scores, reverse=True)
    assert len(experts) <= 5


def test_experts_need_some_evidence(brain):
    for e in tools.who_knows("svc:ledger-svc", 20):
        assert any(e.reasons.values()), e


def test_ledger_svc_is_the_bus_factor_risk(brain):
    # Planted pattern 2: only ines has shipped commits to ledger-svc.
    assert [(r.service_id, r.tier, r.sole_author) for r in tools.bus_factor()] == [
        ("svc:ledger-svc", 1, "ines")
    ]


def test_bus_factor_covers_lower_tiers_on_request(brain):
    risks = {r.service_id for r in tools.bus_factor(max_tier=3)}
    assert "svc:ledger-svc" in risks
    assert all(r.tier <= 3 for r in tools.bus_factor(max_tier=3))


def test_kafka_is_the_most_fragile_service(brain):
    top = tools.fragile_services(3)

    assert [s.id for s in top][0] == "svc:kafka"
    assert top[0].fragility > top[1].fragility >= top[2].fragility
    assert top[0].name == "kafka" and top[0].criticality > 0


@pytest.mark.parametrize(
    "call",
    [
        lambda: tools.who_knows("svc:nope"),
        lambda: tools.who_knows("svc:payments-db", 0),
        lambda: tools.bus_factor(0),
        lambda: tools.bus_factor(4),
        lambda: tools.fragile_services(0),
    ],
)
def test_bad_input_is_a_tool_error(brain, call):
    with pytest.raises(ToolError):
        call()
