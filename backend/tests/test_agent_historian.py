"""Historian (A06): link_similar writes SIMILAR_TO {score} and back-fills PRECEDENT_FOR onto
decisions already made; the Historian agent finds precedents and the runbook, and hands off."""

import itertools

import pytest

from pagersage.agents import orchestrator
from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import ToolError
from tests.fake_claude import FakeClaude, reply, use

PATH = ["svc:checkout-api", "svc:payments-svc", "svc:payments-db"]
_ids = itertools.count(90)


@pytest.fixture
def incident(writer):
    """A fresh triaged incident (with its embedding) per test."""
    iid = f"INC-{next(_ids):03d}"
    writer.query("CREATE (:Incident {id:$id, status:'open', opened_at:1792500000})", {"id": iid})
    tools.set_triage(
        iid,
        "checkout-api errors: payments-db connection pool exhausted",
        "sev1",
        PATH,
        "payments-svc cannot get connections from payments-db; checkout fails.",
    )
    return iid


def _similar(g, iid):
    return g.ro_query(
        "MATCH (:Incident {id:$i})-[s:SIMILAR_TO]->(o) RETURN o.id, s.score ORDER BY o.id",
        {"i": iid},
    ).result_set


def test_link_similar_writes_the_score(writer, incident):
    tools.link_similar(incident, "INC-042", 0.8)
    tools.link_similar(incident, "INC-031", 0.7)
    tools.link_similar(incident, "INC-042", 0.85)

    assert _similar(writer, incident) == [["INC-031", 0.7], ["INC-042", 0.85]]


def test_link_similar_back_fills_precedents(writer, incident):
    past = tools.record_decision("INC-042", AgentName.INVESTIGATOR, "pool cut", "w", 0.9, [])
    now = tools.record_decision(incident, AgentName.INVESTIGATOR, "cfg-0061", "w", 0.9, [])

    tools.link_similar(incident, "INC-042", 0.8)

    assert writer.ro_query(
        "MATCH (p:Decision)-[:PRECEDENT_FOR]->(d:Decision {id:$d}) RETURN p.id", {"d": now}
    ).result_set == [[past]]


@pytest.mark.parametrize(
    ("other", "score", "hint"),
    [("INC-999", 0.5, "INC-999"), ("SELF", 0.5, "different"), ("INC-042", -0.1, "between")],
)
def test_bad_input_is_a_tool_error(writer, incident, other, score, hint):
    with pytest.raises(ToolError, match=hint):
        tools.link_similar(incident, incident if other == "SELF" else other, score)

    assert _similar(writer, incident) == []


def test_historian_links_precedents_and_picks_the_runbook(writer, incident):
    api = FakeClaude(
        [
            reply(use("similar_incidents", path_service_ids=PATH, limit=3)),
            reply(
                use("link_similar", other_incident_id="INC-042", score=0.81),
                use("link_similar", other_incident_id="INC-031", score=0.78),
            ),
            reply(use("best_runbook", service_id="svc:payments-db", limit=3)),
            reply(
                use(
                    "record_decision",
                    what="Repeats INC-042; run rb:raise-payments-db-pool (3/3)",
                    why="Same path and a pool cut on payments-db each time",
                    confidence=0.85,
                    evidence_ids=["INC-042", "INC-031", "rb:raise-payments-db-pool"],
                    policy_ids=[],
                )
            ),
            reply(use("handoff", note="Run raise-payments-db-pool", state_patch_json="{}")),
        ]
    )

    assert orchestrator.run_agent(AgentName.HISTORIAN, incident, api=api).ok

    assert [r[0] for r in _similar(writer, incident)] == ["INC-031", "INC-042"]
    similar = api.requests[1]["messages"][-1]["content"][0]["content"]
    assert similar.index('"INC-042"') < similar.index('"INC-019"')  # graph-ranked first
    runbooks = api.requests[3]["messages"][-1]["content"][0]["content"]
    assert runbooks.startswith('[{"id": "rb:raise-payments-db-pool"')
    kinds = writer.ro_query(
        "MATCH (e:Event {incident_id:$i}) RETURN e.kind ORDER BY e.seq", {"i": incident}
    ).result_set
    assert [k[0] for k in kinds] == [
        "status",
        "tool_call",
        "finding",
        "finding",
        "tool_call",
        "decision",
        "handoff",
    ]
