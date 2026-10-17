"""Claude client wrapper (task A01): one agent's tool-use loop.

The model gotchas from build-plan.md section 2, in one place:
- Model per agent from settings (Haiku 5.5 for Triage and Responder, Sonnet 5.5 for the rest);
  adaptive thinking everywhere; effort `low` on the Haiku agents.
- No temperature / top_p / top_k and no prefill (Haiku 5.5 rejects them); `tool_choice: auto`
  (Sonnet 5.5 rejects forced tool choice). Agents are told to finish by calling a tool.
- The system prompt is cached (tools come before it, so one breakpoint covers both); the
  top-level `cache_control` caches the growing conversation between loop turns.
- `stop_reason` is checked before content; a refusal ends the run (the caller marks the
  incident needs_human). Content is read by block type, and thinking blocks go back unchanged.
- At most MAX_TOOL_CALLS tool calls and TIMEOUT seconds per run.
"""

import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import anthropic

from pagersage.config import get_settings
from pagersage.contracts.schema import AgentName

MAX_TOOL_CALLS = 15
TIMEOUT = 180.0  # seconds per agent run
MAX_TOKENS = 16_000  # room for adaptive thinking plus the answer
EFFORT: dict[AgentName, str] = {AgentName.TRIAGE: "low", AgentName.RESPONDER: "low"}
NUDGE = "You stopped without calling {tools}. Finish now by calling it."


class AgentError(Exception):
    """The agent cannot run at all (no API key)."""


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Tool:
    """What the loop needs from a tool: the API definition and a runner (task A02 builds them)."""

    name: str
    definition: dict[str, Any]
    run: Callable[[dict[str, Any]], ToolOutcome]


Stop = Literal["done", "refusal", "tool_cap", "timeout", "max_tokens", "no_finish"]


@dataclass(frozen=True)
class RunResult:
    stop: Stop
    text: str = ""
    tool_calls: int = 0
    finished_with: str | None = None

    @property
    def ok(self) -> bool:
        return self.stop == "done"


def model_for(agent: AgentName) -> str:
    return getattr(get_settings(), f"model_{AgentName(agent).value}")


@lru_cache(maxsize=1)
def client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise AgentError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=key, max_retries=2)


def request_params(agent: AgentName, system: str, tools: list[Tool]) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": model_for(agent),
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "tools": [t.definition for t in tools],
        "tool_choice": {"type": "auto"},
        "thinking": {"type": "adaptive"},
        "cache_control": {"type": "ephemeral"},
    }
    if effort := EFFORT.get(AgentName(agent)):
        params["output_config"] = {"effort": effort}
    return params


def run(
    agent: AgentName,
    system: str,
    user: str,
    tools: list[Tool],
    *,
    finish: Collection[str] = (),
    api: Any = None,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    """Loop until the agent calls a `finish` tool successfully (or, with no finish tools, stops
    calling tools). One nudge if it stops early; then `no_finish`."""
    api = api or client()
    by_name = {t.name: t for t in tools}
    params = request_params(agent, system, tools)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
    deadline = clock() + TIMEOUT
    calls, nudged, text = 0, False, ""
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return RunResult("timeout", text, calls)
        try:
            resp = api.messages.create(**params, messages=messages, timeout=remaining)
        except anthropic.APITimeoutError:
            return RunResult("timeout", text, calls)
        if resp.stop_reason == "refusal":
            return RunResult("refusal", text, calls)
        text = "".join(b.text for b in resp.content if b.type == "text") or text
        if resp.stop_reason == "max_tokens":
            return RunResult("max_tokens", text, calls)
        uses = [b for b in resp.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": resp.content})
        if not uses:
            if not finish:
                return RunResult("done", text, calls)
            if nudged:
                return RunResult("no_finish", text, calls)
            nudged = True
            messages.append({"role": "user", "content": NUDGE.format(tools=" or ".join(finish))})
            continue
        results, finished = [], None
        for use in uses:
            if calls >= MAX_TOOL_CALLS:
                return RunResult("tool_cap", text, calls)
            calls += 1
            tool = by_name.get(use.name)
            out = tool.run(use.input) if tool else ToolOutcome(f"No tool named {use.name}.", True)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": use.id,
                    "content": out.content,
                    "is_error": out.is_error,
                }
            )
            if use.name in finish and not out.is_error:
                finished = use.name
        if finished:
            return RunResult("done", text, calls, finished)
        messages.append({"role": "user", "content": results})
