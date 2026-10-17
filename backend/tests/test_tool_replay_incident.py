"""G17 replay_incident: every decision (evidence, precedents, policies) and handoff, in order."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import ToolError

A = AgentName


@pytest.fixture(scope="module")
def traced(write_graph):
    """INC-051 run through a short pipeline with a precedent on INC-042."""
    from pagersage import db

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(db, "get_graph", lambda name=None: write_graph)
        mp.setattr(tools, "_now", iter(range(1_792_500_000, 1_792_600_000, 10)).__next__)
        write_graph.query(
            "MATCH (old:Incident {id:'INC-042'}), (new:Incident {id:'INC-051'}) "
            "MERGE (new)-[:SIMILAR_TO {score:0.67}]->(old) "
            "CREATE (:Decision {id:'dec:INC-042:1', what:'raise the pool', why:'it worked', "
            "confidence:0.9, ts:1})-[:ABOUT]->(old)"
        )
        tools.handoff("INC-051", A.TRIAGE, A.INVESTIGATOR, "payments-db is sick", {})
        tools.record_decision(
            "INC-051",
            A.INVESTIGATOR,
            "pool cut is the cause",
            "top suspect",
            0.8,
            ["cfg-0050", "svc:payments-db"],
        )
        tools.handoff("INC-051", A.INVESTIGATOR, A.HISTORIAN, "cause: pool cut", {})
        tools.record_decision(
            "INC-051",
            A.RESPONDER,
            "page priya, wait for ack",
            "tier-1 rollback policy",
            0.9,
            [],
            ["pol:tier1-rollback-ack"],
        )
    return write_graph


def test_decisions_and_handoffs_come_back_in_order(traced, writer):
    r = tools.replay_incident("INC-051")

    assert (r.incident_id, r.status) == ("INC-051", "investigating")
    assert [(d.id, d.agent) for d in r.decisions] == [
        ("dec:INC-051:1", "investigator"),
        ("dec:INC-051:2", "responder"),
    ]
    assert [(h.id, h.from_agent, h.to_agent, h.note) for h in r.handoffs] == [
        ("ho:INC-051:1", "triage", "investigator", "payments-db is sick"),
        ("ho:INC-051:2", "investigator", "historian", "cause: pool cut"),
    ]
    assert r.event_count == 2  # the two handoff events


def test_each_decision_carries_evidence_precedents_and_policies(traced, writer):
    first, second = tools.replay_incident("INC-051").decisions

    assert sorted(first.evidence) == ["cfg-0050", "svc:payments-db"]
    assert first.precedents == ["dec:INC-042:1"]
    assert (first.what, first.why) == ("pool cut is the cause", "top suspect")
    assert first.confidence == 0.8
    assert (second.evidence, second.policies) == ([], ["pol:tier1-rollback-ack"])


def test_a_past_incident_replays_its_timeline_size(traced, writer):
    r = tools.replay_incident("INC-011")

    assert (r.decisions, r.handoffs, r.status) == ([], [], "resolved")
    assert r.event_count == 5


def test_unknown_incident_is_a_tool_error(writer):
    with pytest.raises(ToolError):
        tools.replay_incident("INC-999")
