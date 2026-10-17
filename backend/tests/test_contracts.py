import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from pagersage import queries
from pagersage.contracts import schema, tools
from pagersage.contracts.events import AgentEvent, EventKind, Highlight
from pagersage.contracts.seed import History, SeedBundle, load_seed_dir

EXAMPLES = Path(__file__).resolve().parents[2] / "kestrel-pay" / "company" / "examples"


# ── seed formats ──────────────────────────────────────────────────────────


def test_seed_examples_are_valid():
    bundle = load_seed_dir(EXAMPLES)
    assert {s.name for s in bundle.topology.services} >= {"payments-svc", "payments-db"}
    assert bundle.runbooks.runbooks[0].service == "payments-db"
    assert bundle.policies.policies[0].actions == [schema.ActionKind.ROLLBACK]


def _example_data() -> dict:
    b = load_seed_dir(EXAMPLES)
    return b.model_dump(mode="json")


def test_seed_rejects_dependency_on_unknown_service():
    data = _example_data()
    data["topology"]["services"][0]["depends_on"].append(
        {"to": "ghost-svc", "calls_per_min": 1, "p99_ms": 1}
    )
    with pytest.raises(ValidationError, match="unknown service 'ghost-svc'"):
        SeedBundle.model_validate(data)


def test_seed_rejects_service_without_owner():
    data = _example_data()
    data["org"]["teams"][0]["owns"].remove("kafka")
    with pytest.raises(ValidationError, match="no owning team"):
        SeedBundle.model_validate(data)


def test_seed_rejects_on_call_from_another_team():
    data = _example_data()
    data["org"]["on_call"]["teams"]["checkout"].append("jin")
    with pytest.raises(ValidationError, match="jin is on call for checkout"):
        SeedBundle.model_validate(data)


def test_seed_rejects_unknown_timezone():
    data = _example_data()
    data["org"]["people"][0]["timezone"] = "Mars/Olympus"
    with pytest.raises(ValidationError, match="Unknown IANA timezone"):
        SeedBundle.model_validate(data)


# ── history formats ───────────────────────────────────────────────────────


def _history() -> dict:
    """The smallest history that uses every record type, against the example company."""
    t = 1_757_000_000
    return {
        "deploys": [
            {"id": "dep-0001", "service": "payments-svc", "version": "v1.0.1", "ts": t,
             "deployed_by": "priya", "commits": ["a1b2c3d"]},
        ],
        "commits": [
            {"sha": "a1b2c3d", "message": "Retry soft declines once", "author": "tomas",
             "ts": t - 600, "files_changed": 2, "lines_changed": 40},
        ],
        "config_changes": [
            {"id": "cfg-0001", "service": "payments-db", "key": "max_pool_size", "old": "200",
             "new": "90", "ts": t + 60, "made_by": "tomas"},
        ],
        "incidents": [
            {"id": "INC-042", "title": "Pool exhausted", "severity": "sev1",
             "opened_at": t + 900, "resolved_at": t + 2100, "summary": "Pool cut to 90.",
             "affected": ["payments-db", "checkout-api"],
             "caused_by": [{"change": "cfg-0001", "confidence": 1.0}],
             "alerts": [{"id": "alt-00001", "service": "checkout-api", "signal": "error_rate",
                         "value": 8.6, "threshold": 1.0, "severity": "sev1", "ts": t + 900}],
             "timeline": [{"ts": t + 900, "kind": "status", "text": "Opened."},
                          {"ts": t + 2100, "kind": "status", "text": "Resolved."}],
             "runbooks": [{"runbook": "raise-payments-db-pool", "worked": True, "ts": t + 1600}],
             "resolved_by": "priya",
             "postmortem": {"title": "Pool", "body": "...", "ts": t + 90_000, "author": "priya"}},
        ],
    }  # fmt: skip


def _check_history(data: dict) -> History:
    return History.model_validate(data, context={"seed": load_seed_dir(EXAMPLES)})


def test_history_minimal_is_valid():
    h = _check_history(_history())
    assert h.incidents[0].status == schema.IncidentStatus.RESOLVED
    assert h.deploys[0].status == schema.DeployStatus.OK
    assert schema.postmortem_id(h.incidents[0].id) == "pm:INC-042"


def test_history_rejects_commit_shipped_twice():
    data = _history()
    data["deploys"].append({**data["deploys"][0], "id": "dep-0002"})
    with pytest.raises(ValidationError, match="more than one deploy"):
        _check_history(data)


def test_history_rejects_commit_newer_than_its_deploy():
    data = _history()
    data["commits"][0]["ts"] = data["deploys"][0]["ts"] + 1
    with pytest.raises(ValidationError, match="made after the deploy"):
        _check_history(data)


def test_history_rejects_unknown_cause():
    data = _history()
    data["incidents"][0]["caused_by"][0]["change"] = "cfg-0099"
    with pytest.raises(ValidationError, match="unknown change 'cfg-0099'"):
        _check_history(data)


def test_history_rejects_runbook_outside_incident():
    data = _history()
    data["incidents"][0]["runbooks"][0]["ts"] = data["incidents"][0]["resolved_at"] + 1
    with pytest.raises(ValidationError, match="outside the incident"):
        _check_history(data)


def test_history_checks_people_only_with_seed():
    data = _history()
    data["commits"][0]["author"] = "ghost"
    History.model_validate(data)  # no seed: references are not checked
    with pytest.raises(ValidationError, match="unknown person 'ghost'"):
        _check_history(data)


# ── IDs ───────────────────────────────────────────────────────────────────


def test_id_helpers():
    assert schema.service_id("payments-svc") == "svc:payments-svc"
    assert schema.incident_id(42) == "INC-042"
    assert schema.deploy_id(193) == "dep-0193"
    assert schema.commit_id("a1b2c3") == "a1b2c3"
    assert schema.event_id("INC-042", 7) == "evt:INC-042:7"
    with pytest.raises(ValueError):
        schema.service_id("Payments Svc")


# ── agent events ──────────────────────────────────────────────────────────


def _event() -> AgentEvent:
    return AgentEvent(
        incident_id="INC-107",
        seq=3,
        ts=1_760_000_000,
        agent=schema.AgentName.INVESTIGATOR,
        kind=EventKind.FINDING,
        summary="payments-db config change is the top suspect",
        data={"change_id": "cfg-0061", "score": 0.82},
        highlight=Highlight(
            nodes=["svc:checkout-api", "svc:payments-db", "cfg-0061"],
            edges=[("svc:checkout-api", "DEPENDS_ON", "svc:payments-svc")],
        ),
    )


def test_event_sse_framing():
    sse = _event().to_sse()
    assert sse.startswith("id: 3\nevent: agent\ndata: {")
    assert sse.endswith("}\n\n")


def test_event_node_round_trip():
    ev = _event()
    props = ev.to_node_props()
    assert props["id"] == "evt:INC-107:3"
    assert all(not isinstance(v, dict) for v in props.values()), "graph props must be flat"
    assert AgentEvent.from_node_props(props) == ev


def test_event_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AgentEvent.model_validate({**_event().model_dump(), "colour": "red"})


# ── tools ─────────────────────────────────────────────────────────────────


def test_every_agent_tool_exists_and_is_documented():
    names = {n for ts in tools.AGENT_TOOLS.values() for n in ts} | set(tools.SYSTEM_FUNCTIONS)
    for name in names:
        fn = getattr(tools, name, None)
        assert callable(fn), f"{name} is listed but not defined"
        assert inspect.getdoc(fn), f"{name} needs a docstring (it becomes the tool description)"
        assert inspect.signature(fn).return_annotation is not inspect.Signature.empty


def test_every_agent_has_tools():
    assert set(tools.AGENT_TOOLS) == set(schema.AgentName)


def test_handoff_is_how_pipeline_agents_finish():
    for agent in ("triage", "investigator", "historian", "responder"):
        assert "handoff" in tools.AGENT_TOOLS[schema.AgentName(agent)]


def test_stubs_name_their_task():
    # Via _todo itself, so this test outlives any one stub being implemented.
    with pytest.raises(NotImplementedError, match="task G99 on the PagerSage task board"):
        tools._todo("G99")


# ── query loader ──────────────────────────────────────────────────────────


def test_query_loader_rejects_bad_names():
    for bad in ("../secrets", "Suspect", "a/b", ""):
        with pytest.raises(ValueError):
            queries.load(bad)


def test_query_loader_reports_missing_query():
    with pytest.raises(FileNotFoundError, match="no_such_query"):
        queries.load("no_such_query")
