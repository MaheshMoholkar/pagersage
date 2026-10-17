"""Tool registry (A02): strict tool definitions from contracts/tools.py, bound arguments, and
errors returned to the agent as hints."""

import json

import pytest

from pagersage.agents import registry
from pagersage.agents.registry import RunContext
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import AGENT_TOOLS
from tests.scenario import NOW, SINCE

TRI, INV = AgentName.TRIAGE, AgentName.INVESTIGATOR


def _objects(schema):
    """Every object schema inside a JSON schema."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for v in schema.values():
            yield from _objects(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _objects(v)


@pytest.mark.parametrize("agent", list(AGENT_TOOLS))
def test_every_tool_is_strict_with_a_description(agent):
    ctx = RunContext(agent, incident_id="INC-051", next_agent=AgentName.SCRIBE)

    for tool in registry.tools_for(ctx):
        d = tool.definition
        assert d["strict"] is True and d["description"], tool.name
        assert all(o["additionalProperties"] is False for o in _objects(d["input_schema"]))


def test_bound_arguments_are_not_in_the_schema():
    ctx = RunContext(INV, incident_id="INC-051", next_agent=AgentName.HISTORIAN)
    props = {t.name: t.definition["input_schema"]["properties"] for t in registry.tools_for(ctx)}

    assert set(props["record_cause"]) == {"change_id", "confidence"}
    assert set(props["record_decision"]) == {
        "what",
        "why",
        "confidence",
        "evidence_ids",
        "policy_ids",
    }
    assert set(props["handoff"]) == {"note", "state_patch_json"}


def test_without_an_incident_the_agent_names_it():
    [replay] = [
        t for t in registry.tools_for(RunContext(AgentName.BRAIN)) if t.name == "replay_incident"
    ]

    assert replay.definition["input_schema"]["required"] == ["incident_id"]


def _run(ctx, name, **raw):
    [tool] = [t for t in registry.tools_for(ctx) if t.name == name]
    return tool.run(raw)


def test_results_come_back_as_json(tool_graph):
    out = _run(RunContext(TRI, "INC-051", INV), "find_service", q="payments db")

    assert not out.is_error
    assert json.loads(out.content)[0]["id"] == "svc:payments-db"


def test_tool_errors_carry_their_hint(tool_graph):
    out = _run(RunContext(TRI, "INC-051", INV), "blast_radius", service_id="svc:nope")

    assert out.is_error and "find_service" in out.content


def test_bad_arguments_are_errors_not_crashes(tool_graph):
    out = _run(RunContext(TRI, "INC-051", INV), "blast_radius", service_id=7, extra=1)

    assert out.is_error and out.content.startswith("Bad arguments")


def test_empty_suspects_tell_the_agent_to_widen_the_window(scenario):
    ctx = RunContext(INV, "INC-051", AgentName.HISTORIAN)

    assert not _run(ctx, "suspect_changes", service_id="svc:checkout-api", since=SINCE).is_error
    out = _run(ctx, "suspect_changes", service_id="svc:checkout-api", since=NOW)
    assert out.is_error and "widen" in out.content


def test_unexpected_exceptions_become_errors(tool_graph, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("redis went away")

    monkeypatch.setattr(registry.tools, "fragile_services", boom)

    out = _run(RunContext(AgentName.BRAIN), "fragile_services")

    assert out.is_error and "Internal error" in out.content


def test_handoff_binds_the_agents_and_parses_the_state(writer):
    calls = []
    ctx = RunContext(TRI, "INC-051", INV, on_call=calls.append)

    out = _run(ctx, "handoff", note="payments-db is sick", state_patch_json='{"sev": "sev1"}')
    bad = _run(ctx, "handoff", note="x", state_patch_json="[1, 2]")

    assert json.loads(out.content).startswith("ho:INC-051:")
    assert bad.is_error and "JSON object" in bad.content
    [[state, assigned]] = writer.ro_query(
        "MATCH (i:Incident {id:'INC-051'})-[:ASSIGNED_TO]->(a:Agent) RETURN i.state, a.name"
    ).result_set
    assert json.loads(state)["sev"] == "sev1" and assigned == "investigator"
    assert [(c.tool, c.agent, c.error is None) for c in calls] == [
        ("handoff", TRI, True),
        ("handoff", TRI, False),
    ]
