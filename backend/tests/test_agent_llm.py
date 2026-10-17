"""Claude client wrapper (A01): request shape and the tool-use loop, against a scripted fake."""

import itertools

import pytest

from pagersage.agents import llm
from pagersage.agents.llm import Tool, ToolOutcome
from pagersage.contracts.schema import AgentName
from tests.fake_claude import FakeClaude, reply, text, thinking, use


def _tool(name, seen=None):
    def run(input):
        if seen is not None:
            seen.append((name, input))
        return ToolOutcome("{}")

    return Tool(name=name, definition={"name": name, "input_schema": {"type": "object"}}, run=run)


def test_haiku_agents_run_at_low_effort_with_adaptive_thinking():
    params = llm.request_params(AgentName.TRIAGE, "You are Triage.", [_tool("a"), _tool("b")])

    assert params["model"] == "claude-haiku-5-5"
    assert params["output_config"] == {"effort": "low"}
    assert params["thinking"] == {"type": "adaptive"}
    assert params["tool_choice"] == {"type": "auto"}
    assert params["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert params["cache_control"] == {"type": "ephemeral"}
    assert not {"temperature", "top_p", "top_k"} & params.keys()


def test_sonnet_agents_keep_the_default_effort():
    params = llm.request_params(AgentName.INVESTIGATOR, "x", [])

    assert params["model"] == "claude-sonnet-5-5"
    assert "output_config" not in params


def test_loop_runs_tools_and_passes_thinking_back_unchanged():
    seen = []
    first = reply(thinking("look it up"), use("find_service", q="checkout"))
    api = FakeClaude([first, reply(text("found it"), use("handoff", note="done"))])

    result = llm.run(
        AgentName.TRIAGE,
        "sys",
        "INC-051",
        [_tool("find_service", seen=seen), _tool("handoff", seen=seen)],
        finish={"handoff"},
        api=api,
    )

    assert result == llm.RunResult("done", "found it", 2, "handoff")
    assert seen == [("find_service", {"q": "checkout"}), ("handoff", {"note": "done"})]
    second = api.requests[1]["messages"]
    assert second[1] == {"role": "assistant", "content": first.content}  # thinking block intact
    [tool_result] = second[2]["content"]
    assert tool_result["tool_use_id"] == first.content[1].id
    assert tool_result["is_error"] is False


def test_a_failed_finish_tool_does_not_end_the_run():
    bad, good = ToolOutcome("No incident", is_error=True), ToolOutcome("{}")
    outcomes = iter([bad, good])
    handoff = Tool("handoff", {"name": "handoff"}, lambda _: next(outcomes))
    api = FakeClaude([reply(use("handoff")), reply(use("handoff"))])

    result = llm.run(AgentName.TRIAGE, "s", "u", [handoff], finish={"handoff"}, api=api)

    assert result.ok and result.tool_calls == 2
    assert api.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_unknown_tools_come_back_as_errors():
    api = FakeClaude([reply(use("drop_database")), reply(text("sorry"))])

    result = llm.run(AgentName.BRAIN, "s", "u", [], api=api)

    assert result.ok
    assert api.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_an_agent_that_stops_early_is_nudged_once():
    api = FakeClaude([reply(text("I think it's the pool.")), reply(text("Still no."))])

    result = llm.run(AgentName.TRIAGE, "s", "u", [_tool("handoff")], finish={"handoff"}, api=api)

    assert result.stop == "no_finish"
    assert "handoff" in api.requests[1]["messages"][-1]["content"]


def test_refusal_stops_before_reading_content():
    api = FakeClaude([reply(text("partial"), stop_reason="refusal")])

    assert llm.run(AgentName.TRIAGE, "s", "u", [], api=api).stop == "refusal"


def test_tool_calls_are_capped(monkeypatch):
    monkeypatch.setattr(llm, "MAX_TOOL_CALLS", 3)
    api = FakeClaude([reply(use("t"), use("t")) for _ in range(3)])

    result = llm.run(AgentName.TRIAGE, "s", "u", [_tool("t")], api=api)

    assert result.stop == "tool_cap" and result.tool_calls == 3


def test_runs_time_out():
    ticks = itertools.count(0, llm.TIMEOUT / 2)  # each clock read moves half the budget
    api = FakeClaude([reply(use("t")) for _ in range(5)])

    result = llm.run(AgentName.TRIAGE, "s", "u", [_tool("t")], api=api, clock=lambda: next(ticks))

    assert result.stop == "timeout"


def test_no_api_key_is_an_agent_error(monkeypatch):
    llm.client.cache_clear()
    monkeypatch.setattr(llm, "get_settings", lambda: type("S", (), {"anthropic_api_key": None}))
    with pytest.raises(llm.AgentError):
        llm.client()
    llm.client.cache_clear()
