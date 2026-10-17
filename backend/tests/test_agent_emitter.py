"""Agent event emitter (A11): one timeline event per tool call, in the agreed event format."""

from pagersage.agents import emitter, registry
from pagersage.agents.registry import RunContext, ToolCall
from pagersage.contracts import tools
from pagersage.contracts.events import EventKind, Highlight
from pagersage.contracts.schema import ActionKind, AgentName, ChangeType

INV = AgentName.INVESTIGATOR


def _call(tool, value=None, error=None, **input):
    return ToolCall(INV, "INC-051", tool, input, value, error)


def _suspect(cid, sid, score):
    return tools.Suspect(
        change_id=cid,
        change_type=ChangeType.CONFIG,
        service_id=sid,
        ts=1,
        dist=0,
        fragility=0.0,
        score=score,
        score_parts={},
    )


def test_read_tools_become_tool_call_events_that_highlight_what_they_found():
    suspects = [_suspect("cfg-0061", "svc:payments-db", 3.13), _suspect("dep-0417", "svc:x", 1.4)]
    kind, summary, data, highlight = emitter.event_for(
        _call("suspect_changes", suspects, service_id="svc:checkout-api", since=5)
    )

    assert kind == EventKind.TOOL_CALL
    assert summary.startswith("suspect_changes(service_id=svc:checkout-api, since=5): 2 found")
    assert "cfg-0061 (3.13)" in summary
    assert data == {
        "tool": "suspect_changes",
        "input": {"service_id": "svc:checkout-api", "since": 5},
        "ok": True,
        "rows": 2,
    }
    assert highlight.nodes == ["cfg-0061", "svc:payments-db", "dep-0417", "svc:x"]


def test_root_cause_path_highlights_the_whole_path():
    h = Highlight(nodes=["svc:a", "svc:b", "cfg-0061"], edges=[("svc:a", "DEPENDS_ON", "svc:b")])
    path = tools.RootCausePath(
        services=["svc:a", "svc:b"],
        path_weight=115,
        change_id="cfg-0061",
        commits=[],
        authors=[],
        highlight=h,
    )

    _, summary, _, highlight = emitter.event_for(_call("root_cause_path", path))

    assert summary == "Root-cause path a → b → cfg-0061 (weight 115)"
    assert highlight == h


def test_decisions_findings_actions_and_errors():
    input = {"what": "Pool cut", "why": "w", "confidence": 0.9, "evidence_ids": ["cfg-0061"]}
    decision = _call("record_decision", "dec:INC-051:1", **input)
    cause = _call("record_cause", {"ok": True}, change_id="cfg-0061", confidence=0.9)
    done = tools.ActionResult(action=ActionKind.ROLLBACK, ok=True, detail="Simulated rollback")
    roll = _call("rollback", done, service_id="svc:x", deploy_id="dep-0417")
    failed = _call("blast_radius", None, "No service with id 'svc:nope'", service_id="svc:nope")

    assert emitter.event_for(decision)[:3] == (
        EventKind.DECISION,
        "Decided: Pool cut",
        {"decision_id": "dec:INC-051:1", "confidence": 0.9, "what": "Pool cut"},
    )
    kind, _, _, h = emitter.event_for(cause)
    assert kind == EventKind.FINDING and h.edges == [("INC-051", "CAUSED_BY", "cfg-0061")]
    assert emitter.event_for(roll)[:2] == (EventKind.ACTION, "Simulated rollback")
    kind, summary, data, _ = emitter.event_for(failed)
    assert kind == EventKind.ERROR and data["hint"].startswith("No service")


def test_self_logging_tools_add_nothing():
    assert emitter.event_for(_call("handoff", "ho:INC-051:1", note="x")) is None
    assert emitter.event_for(_call("page_owner", {"ok": True}, handle="priya")) is None


def _tool(ctx, name):
    [tool] = [t for t in registry.tools_for(ctx) if t.name == name]
    return tool


def test_calls_land_on_the_timeline_through_the_registry(writer):
    count = "MATCH (e:Event {incident_id:'INC-051'}) RETURN count(e)"
    [[before]] = writer.ro_query(count).result_set
    triage = RunContext(AgentName.TRIAGE, "INC-051", INV, on_call=emitter.on_call)
    investigator = RunContext(INV, "INC-051", AgentName.HISTORIAN, on_call=emitter.on_call)

    _tool(triage, "blast_radius").run({"service_id": "svc:payments-db"})
    _tool(triage, "blast_radius").run({"service_id": "svc:nope"})
    _tool(investigator, "record_decision").run(
        {"what": "w", "why": "y", "confidence": 2.0, "evidence_ids": []}
    )

    rows = writer.ro_query(
        "MATCH (e:Event {incident_id:'INC-051'}) WHERE e.seq > $n "
        "RETURN e.kind, e.agent ORDER BY e.seq",
        {"n": before},
    ).result_set
    assert rows == [["tool_call", "triage"], ["error", "triage"], ["error", "investigator"]]


def test_runs_without_an_incident_emit_nothing(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("no timeline for Brain")

    monkeypatch.setattr(tools, "append_event", fail)
    emitter.on_call(ToolCall(AgentName.BRAIN, None, "fragile_services", {}, []))
