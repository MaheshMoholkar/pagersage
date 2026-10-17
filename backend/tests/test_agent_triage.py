"""Triage (A04): set_triage writes title, severity, summary, AFFECTED and the embedding; the
Triage agent sizes the incident with find_service / blast_radius and hands off."""

import itertools

import pytest

from pagersage.agents import orchestrator
from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import ToolError
from tests.fake_claude import FakeClaude, reply, use

_ids = itertools.count(80)
TITLE = "checkout-api errors: payments-db connection pool exhausted"
SUMMARY = "payments-svc cannot get connections from payments-db; checkout fails."


@pytest.fixture
def incident(writer):
    iid = f"INC-{next(_ids):03d}"
    writer.query(
        "MATCH (s:Service {id:'svc:payments-db'}) "
        "CREATE (i:Incident {id:$id, title:'payments-db saturation 0.97', severity:'sev2', "
        "status:'open', opened_at:1792500000, summary:''}), "
        "(a:Alert {id:$aid, ts:1792500000, signal:'saturation', value:0.97, threshold:0.9, "
        "severity:'sev2'})-[:PART_OF]->(i), (a)-[:FIRED_ON]->(s)",
        {"id": iid, "aid": f"alt-8{iid[-3:]}"},
    )
    return iid


def _triaged(g, iid):
    return g.ro_query(
        "MATCH (i:Incident {id:$i}) OPTIONAL MATCH (i)-[:AFFECTED]->(s:Service) "
        "RETURN i.title, i.severity, i.summary, i.status, i.embedding IS NOT NULL, "
        "collect(s.id)",
        {"i": iid},
    ).result_set[0]


def test_set_triage_writes_the_incident_and_its_embedding(writer, incident):
    tools.set_triage(incident, TITLE, "sev1", ["svc:payments-db", "svc:checkout-api"], SUMMARY)

    title, severity, summary, status, embedded, affected = _triaged(writer, incident)
    assert (title, severity, summary, status, embedded) == (
        TITLE,
        "sev1",
        SUMMARY,
        "investigating",
        True,
    )
    assert sorted(affected) == ["svc:checkout-api", "svc:payments-db"]


def test_the_embedding_finds_the_pool_precedents(writer, incident):
    tools.set_triage(incident, TITLE, "sev1", ["svc:payments-db"], SUMMARY)

    path = ["svc:checkout-api", "svc:payments-svc", "svc:payments-db"]
    found = tools.similar_incidents(incident, path)

    assert [i.id for i in found.graph_ranked] == ["INC-042", "INC-031", "INC-019"]


def test_triage_again_does_not_duplicate_affected(writer, incident):
    tools.set_triage(incident, TITLE, "sev2", ["svc:payments-db"], SUMMARY)
    tools.set_triage(incident, TITLE, "sev1", ["svc:payments-db", "svc:payments-db"], SUMMARY)

    assert _triaged(writer, incident)[5] == ["svc:payments-db"]
    assert _triaged(writer, incident)[1] == "sev1"


@pytest.mark.parametrize(
    ("severity", "services", "title", "hint"),
    [
        ("sev9", ["svc:payments-db"], TITLE, "severity"),
        ("sev1", [], TITLE, "at least one"),
        ("sev1", ["svc:nope"], TITLE, "svc:nope"),
        ("sev1", ["svc:payments-db"], "  ", "empty"),
    ],
)
def test_bad_input_writes_nothing(writer, incident, severity, services, title, hint):
    with pytest.raises(ToolError, match=hint):
        tools.set_triage(incident, title, severity, services, SUMMARY)

    assert _triaged(writer, incident)[3] == "open"


def test_unknown_incident_is_a_tool_error(writer):
    with pytest.raises(ToolError, match="No incident"):
        tools.set_triage("INC-999", TITLE, "sev1", ["svc:payments-db"], SUMMARY)


def test_triage_agent_sizes_the_incident_and_hands_off(writer, incident):
    api = FakeClaude(
        [
            reply(use("blast_radius", service_id="svc:payments-db")),
            reply(
                use(
                    "set_triage",
                    title=TITLE,
                    severity="sev1",
                    impacted_service_ids=["svc:payments-db", "svc:checkout-api"],
                    summary=SUMMARY,
                )
            ),
            reply(use("handoff", note="payments-db saturated at 0.97", state_patch_json="{}")),
        ]
    )

    result = orchestrator.run_agent(AgentName.TRIAGE, incident, api=api)

    assert result.ok and result.tool_calls == 3
    assert _triaged(writer, incident)[3] == "investigating"
    kinds = writer.ro_query(
        "MATCH (e:Event {incident_id:$i}) RETURN e.kind ORDER BY e.seq", {"i": incident}
    ).result_set
    assert [k[0] for k in kinds] == ["status", "tool_call", "finding", "handoff"]
