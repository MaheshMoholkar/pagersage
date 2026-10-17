"""Investigator (A05): record_cause writes CAUSED_BY {confidence}; the Investigator agent ranks
suspects, walks the root-cause path, records the cause and a decision naming the rejected decoy,
and hands off. Runs on the module's write graph with the pool-exhaustion scenario injected."""

import pytest

from pagersage.agents import orchestrator
from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import ToolError
from tests import scenario
from tests.fake_claude import FakeClaude, reply, use

PATH = ["svc:checkout-api", "svc:payments-svc", "svc:payments-db"]
STATE = '{"cause": "cfg-0061", "rejected": ["dep-0417"]}'


@pytest.fixture
def live(writer, monkeypatch):
    """The scenario's changes and alert health on the write graph, clock at the first alert."""
    if not writer.ro_query("MATCH (c:ConfigChange {id:'cfg-0061'}) RETURN c.id").result_set:
        writer.query(scenario.SCENARIO, {"now": scenario.NOW})
        for sid, health in scenario.HEALTH.items():
            tools.update_live_weights(sid, health)
    monkeypatch.setattr(tools, "_now", lambda: scenario.NOW)
    return writer


def _causes(g, iid="INC-051"):
    return g.ro_query(
        "MATCH (:Incident {id:$i})-[c:CAUSED_BY]->(x) RETURN x.id, c.confidence ORDER BY x.id",
        {"i": iid},
    ).result_set


def test_record_cause_links_a_config_change_or_a_deploy(live):
    tools.record_cause("INC-051", "cfg-0061", 0.9)
    tools.record_cause("INC-051", "dep-0417", 0.1)
    tools.record_cause("INC-051", "cfg-0061", 0.95)  # again: confidence updated, no new edge

    assert _causes(live) == [["cfg-0061", 0.95], ["dep-0417", 0.1]]


@pytest.mark.parametrize(
    ("iid", "cid", "conf", "hint"),
    [
        ("INC-051", "cfg-9999", 0.5, "suspect_changes"),
        ("INC-051", "svc:payments-db", 0.5, "No change"),
        ("INC-051", "cfg-0061", 1.5, "between 0 and 1"),
        ("INC-999", "cfg-0061", 0.5, "No incident"),
    ],
)
def test_bad_input_is_a_tool_error(live, iid, cid, conf, hint):
    with pytest.raises(ToolError, match=hint):
        tools.record_cause(iid, cid, conf)


def test_investigator_finds_the_pool_cut_and_rejects_the_decoy(live):
    live.query(
        "CREATE (:Incident {id:'INC-052', title:'checkout-api errors', severity:'sev1', "
        "status:'investigating', opened_at:$now, summary:''})",
        {"now": scenario.NOW},
    )
    why = "anomaly 9.5 on payments-db; dep-0417 on checkout-api is a victim (anomaly 1)"
    api = FakeClaude(
        [
            reply(use("suspect_changes", service_id="svc:checkout-api", since=scenario.SINCE)),
            reply(
                use(
                    "root_cause_path",
                    alerting_service_id="svc:checkout-api",
                    suspect_service_id="svc:payments-db",
                    change_id="cfg-0061",
                )
            ),
            reply(use("record_cause", change_id="cfg-0061", confidence=0.9)),
            reply(
                use(
                    "record_decision",
                    what="cfg-0061 (max_pool_size 100 -> 60) caused the incident",
                    why=why,
                    confidence=0.9,
                    evidence_ids=[*PATH, "cfg-0061"],
                    policy_ids=[],
                )
            ),
            reply(use("handoff", note="Cause cfg-0061; rejected dep-0417", state_patch_json=STATE)),
        ]
    )

    result = orchestrator.run_agent(AgentName.INVESTIGATOR, "INC-052", api=api)

    assert result.ok
    assert _causes(live, "INC-052") == [["cfg-0061", 0.9]]
    first_result = api.requests[1]["messages"][-1]["content"][0]["content"]
    assert first_result.index("cfg-0061") < first_result.index("dep-0417")  # ranked first
    [[what, evidence]] = live.ro_query(
        "MATCH (d:Decision)-[:ABOUT]->(:Incident {id:'INC-052'}) "
        "MATCH (d)-[:BASED_ON]->(e) RETURN d.what, collect(e.id)"
    ).result_set
    assert what.startswith("cfg-0061") and sorted(evidence) == sorted([*PATH, "cfg-0061"])
    events = live.ro_query(
        "MATCH (e:Event {incident_id:'INC-052'}) RETURN e.kind, e.highlight ORDER BY e.seq"
    ).result_set
    assert [k for k, _ in events] == [
        "status",
        "tool_call",
        "tool_call",
        "finding",
        "decision",
        "handoff",
    ]
    assert '"DEPENDS_ON"' in events[2][1]  # the root-cause path is highlighted
