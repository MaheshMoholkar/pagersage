"""Orchestrator (A03): Triage → Investigator → Historian → Responder, each starting from the
graph and finishing with handoff; anything else marks the incident needs_human."""

import itertools
import json

import pytest

from pagersage import runtime
from pagersage.agents import orchestrator
from tests.fake_claude import FakeClaude, reply, text, use

_ids = itertools.count(70)


@pytest.fixture
def incident(writer):
    """A fresh incident with one alert on payments-db (the module shares one graph)."""
    iid = f"INC-{next(_ids):03d}"
    writer.query(
        "MATCH (s:Service {id:'svc:payments-db'}) "
        "CREATE (i:Incident {id:$id, title:'payments-db saturation', severity:'sev1', "
        "status:'open', opened_at:1792500000, summary:''}), "
        "(a:Alert {id:$aid, ts:1792500000, signal:'saturation', value:0.97, threshold:0.9, "
        "severity:'sev1'})-[:PART_OF]->(i), (a)-[:FIRED_ON]->(s)",
        {"id": iid, "aid": f"alt-9{iid[-3:]}"},
    )
    return iid


def _handoff(note, **state):
    return reply(use("handoff", note=note, state_patch_json=json.dumps(state)))


def _status(g, iid):
    return g.ro_query("MATCH (i:Incident {id:$i}) RETURN i.status", {"i": iid}).result_set[0][0]


def test_pipeline_runs_every_agent_in_order(writer, incident):
    api = FakeClaude(
        [
            reply(use("blast_radius", service_id="svc:payments-db")),
            _handoff("payments-db saturated at 0.97", alerting=["svc:payments-db"]),
            _handoff("cfg-0061 cut the pool", cause="cfg-0061"),
            _handoff("Repeats INC-042; run raise-payments-db-pool", runbook="rb:x"),
            _handoff("Paged priya; issue opened"),
        ]
    )

    assert orchestrator.run_pipeline(incident, api=api) is True

    handoffs = writer.ro_query(
        "MATCH (h:Handoff)-[:ON]->(:Incident {id:$i}), (h)-[:FROM]->(f), (h)-[:TO]->(t) "
        "RETURN f.name, t.name ORDER BY h.ts, h.id",
        {"i": incident},
    ).result_set
    assert handoffs == [
        ["triage", "investigator"],
        ["investigator", "historian"],
        ["historian", "responder"],
        ["responder", "scribe"],
    ]
    started = writer.ro_query(
        "MATCH (e:Event {incident_id:$i, kind:'status'}) WHERE e.text ENDS WITH 'started' "
        "RETURN e.agent ORDER BY e.seq",
        {"i": incident},
    ).result_set
    assert [r[0] for r in started] == ["triage", "investigator", "historian", "responder"]
    assert _status(writer, incident) == "open"


def test_each_agent_starts_from_the_graph_not_the_transcript(writer, incident):
    api = FakeClaude(
        [
            reply(text("thinking out loud: SECRET-TRIAGE-NOTE"), use("handoff", note="pool")),
            _handoff("cfg-0061", cause="cfg-0061"),
            _handoff("INC-042"),
            _handoff("done"),
        ]
    )

    orchestrator.run_pipeline(incident, api=api)

    triage_brief = api.requests[0]["messages"][0]["content"]
    investigator_brief = api.requests[1]["messages"][0]["content"]
    historian_brief = api.requests[2]["messages"][0]["content"]
    assert f"Incident {incident} [sev1]" in triage_brief
    assert "svc:payments-db saturation 0.97" in triage_brief
    assert "Handoff note from triage: pool" in investigator_brief
    assert "SECRET-TRIAGE-NOTE" not in investigator_brief
    assert len(api.requests[1]["messages"]) == 1  # a fresh conversation
    assert '"cause": "cfg-0061"' in historian_brief
    assert "Handoff note from investigator: cfg-0061" in historian_brief
    assert api.requests[0]["model"] == "claude-haiku-5-5"
    assert api.requests[1]["model"] == "claude-sonnet-5-5"


def test_a_refusal_stops_the_pipeline_and_needs_a_human(writer, incident):
    api = FakeClaude([_handoff("ok"), reply(text("no"), stop_reason="refusal")])

    assert orchestrator.run_pipeline(incident, api=api) is False

    assert _status(writer, incident) == "needs_human"
    assert api.replies == []  # the Historian never ran
    [[text_]] = writer.ro_query(
        "MATCH (e:Event {incident_id:$i, kind:'error'}) RETURN e.text", {"i": incident}
    ).result_set
    assert text_ == "Needs a human: investigator stopped: the model declined to continue"


def test_no_handoff_after_a_nudge_needs_a_human(writer, incident):
    api = FakeClaude([reply(text("I'm done.")), reply(text("Really done."))])

    assert orchestrator.run_pipeline(incident, api=api) is False
    assert _status(writer, incident) == "needs_human"


def test_an_api_error_needs_a_human(writer, incident):
    api = FakeClaude([RuntimeError("overloaded")])

    assert orchestrator.run_pipeline(incident, api=api) is False
    assert _status(writer, incident) == "needs_human"


def test_install_registers_the_hooks_only_with_a_key(monkeypatch):
    settings = type("S", (), {"agents_enabled": True, "anthropic_api_key": None})
    monkeypatch.setattr(orchestrator, "get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator, "_installed", False)
    monkeypatch.setattr(runtime, "_opened", [])
    monkeypatch.setattr(runtime, "_resolved", [])

    assert orchestrator.install() is False
    settings.anthropic_api_key = "sk-test"
    assert orchestrator.install() is True
    assert orchestrator.install() is True  # idempotent
    assert runtime._opened == [orchestrator.run_pipeline]
    assert runtime._resolved == [orchestrator.run_scribe]


def test_tests_never_start_real_agents():
    from pagersage.main import app  # noqa: F401  (importing the app calls install)

    assert orchestrator.run_pipeline not in runtime._opened
