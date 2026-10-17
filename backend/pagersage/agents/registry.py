"""Tool registry (task A02): the tools in contracts/tools.py as strict Claude tools.

- The input schema comes from the function signature (a pydantic model), made strict-valid by
  `anthropic.transform_schema` (unsupported keywords such as defaults move into descriptions),
  and the definition sets `strict: true`. The description is the tool's docstring.
- Bound arguments are filled in here, never by the model, and left out of the schema: the
  run's incident (`incident_id`), the calling agent (`agent`, `from_agent`) and the next agent
  (`to_agent`). An agent can only touch the incident it was given.
- `handoff.state_patch` is free-form JSON, which a strict schema can't express (every object
  needs `additionalProperties: false`), so the model sends it as the string `state_patch_json`.
- Results go back as JSON. A ToolError comes back as an is_error result carrying its hint, and
  so do bad arguments and an empty result from a tool in EMPTY_HINTS. Unexpected exceptions
  are logged and come back as is_error too, so one bad call never kills the agent.
- Prompt-injection hygiene (A13): results are JSON in tool_result blocks, so commit messages
  and alert text reach the model as data; agents write only through these tools; and an
  external action (page, issue, rollback) is refused until check_policy has run for that
  action in the same run.
"""

import inspect
import json
import logging
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Any

import anthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from pagersage.agents.llm import Tool, ToolOutcome
from pagersage.contracts import tools
from pagersage.contracts.schema import ActionKind, AgentName
from pagersage.contracts.tools import AGENT_TOOLS, ToolError

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 20_000

# Empty results that usually mean the agent asked the wrong question.
EMPTY_HINTS = {
    "find_service": "No service matched. Try one word of the name, or a prefix such as 'pay*'.",
    "suspect_changes": "No deploys or config changes in the window: widen `since` "
    "(e.g. 24 hours before the first alert).",
}

# Parameter descriptions the docstrings don't carry.
PARAM_DOCS = {
    "service_id": "Service id, e.g. 'svc:payments-db' (from find_service)",
    "since": "Epoch seconds; changes after this time",
    "confidence": "0 to 1",
    "score": "0 to 1",
    "evidence_ids": "Node ids returned by tools: services, dep-/cfg- ids, commit shas, INC-...",
    "policy_ids": "pol:... ids from check_policy",
    "handle": "Person handle from who_to_page, e.g. 'priya'",
    "change_id": "dep-.... or cfg-.... id from suspect_changes",
    "deploy_id": "dep-.... id of the deploy to undo",
}
# External actions and the policy check each one needs first (A13).
NEEDS_POLICY = {
    "page_owner": ActionKind.PAGE,
    "open_issue": ActionKind.ISSUE,
    "rollback": ActionKind.ROLLBACK,
}

# Never the model's to choose: the clock is the server's.
NOT_EXPOSED = {"now"}
STATE_PATCH_DOC = (
    'JSON object merged into the incident state for the next agents, e.g. {"root_cause": '
    '"cfg-0061", "path": ["svc:checkout-api", "svc:payments-db"]}'
)


@dataclass(frozen=True)
class ToolCall:
    """One finished call, for the event emitter (A11)."""

    agent: AgentName
    incident_id: str | None
    tool: str
    input: dict[str, Any]
    value: Any = None  # what the tool returned (None on error)
    error: str | None = None  # the hint the agent saw, when the call failed


@dataclass
class RunContext:
    agent: AgentName
    incident_id: str | None = None
    next_agent: AgentName | None = None
    on_call: Callable[[ToolCall], None] | None = None
    checked: set[ActionKind] = field(default_factory=set)  # actions check_policy has cleared

    def bound(self, name: str) -> dict[str, Any]:
        params = inspect.signature(getattr(tools, name)).parameters
        values: dict[str, Any] = {
            "agent": self.agent,
            "from_agent": self.agent,
            "to_agent": self.next_agent,
        }
        if self.incident_id is not None:
            values["incident_id"] = self.incident_id
        return {k: v for k, v in values.items() if k in params}


@cache
def input_model(name: str, hidden: frozenset[str]) -> type[BaseModel]:
    fn = getattr(tools, name)
    hints = typing.get_type_hints(fn)
    fields: dict[str, Any] = {}
    for param, p in inspect.signature(fn).parameters.items():
        if param in hidden or param in NOT_EXPOSED:
            continue
        if name == "handoff" and param == "state_patch":
            fields["state_patch_json"] = (str, Field(default="{}", description=STATE_PATCH_DOC))
            continue
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[param] = (hints[param], Field(default=default, description=PARAM_DOCS.get(param)))
    return create_model(f"{name}_input", __config__=ConfigDict(extra="forbid"), **fields)


def definition(name: str, hidden: frozenset[str]) -> dict[str, Any]:
    schema = anthropic.transform_schema(input_model(name, hidden))
    schema.pop("title", None)
    return {
        "name": name,
        "description": inspect.getdoc(getattr(tools, name)),
        "input_schema": schema,
        "strict": True,
    }


def to_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list | tuple):
        return [to_json(v) for v in value]
    if value is None:
        return {"ok": True}
    return value


def _call(name: str, ctx: RunContext, raw: dict[str, Any]) -> tuple[Any, str | None]:
    """Run one tool. Returns (value, None) or (None, hint for the agent)."""
    bound = ctx.bound(name)
    try:
        args = input_model(name, frozenset(bound)).model_validate(raw)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        return None, f"Bad arguments: {problems}"
    kwargs = {k: getattr(args, k) for k in type(args).model_fields} | bound
    if "state_patch_json" in kwargs:
        try:
            kwargs["state_patch"] = json.loads(kwargs.pop("state_patch_json") or "{}")
        except json.JSONDecodeError as e:
            return None, f"state_patch_json is not valid JSON: {e}"
        if not isinstance(kwargs["state_patch"], dict):
            return None, "state_patch_json must be a JSON object"
    if (action := NEEDS_POLICY.get(name)) and action not in ctx.checked:
        return None, (
            f"Refused: call check_policy with action '{action.value}' on the service first, "
            f"then follow the policies it returns before calling {name}."
        )
    try:
        value = getattr(tools, name)(**kwargs)
    except ToolError as e:
        return None, str(e)
    except Exception as e:
        log.exception("tool %s failed for %s", name, ctx.incident_id)
        return None, f"Internal error in {name} ({type(e).__name__}); try another approach."
    if getattr(tools, name) is tools.check_policy:
        ctx.checked.add(ActionKind(kwargs["action"]))
    if value == [] and name in EMPTY_HINTS:
        return value, EMPTY_HINTS[name]
    return value, None


def make_tool(name: str, ctx: RunContext) -> Tool:
    def run(raw: dict[str, Any]) -> ToolOutcome:
        value, hint = _call(name, ctx, raw)
        if ctx.on_call:
            ctx.on_call(ToolCall(ctx.agent, ctx.incident_id, name, raw, value, hint))
        if hint is not None:
            return ToolOutcome(hint, is_error=True)
        return ToolOutcome(json.dumps(to_json(value), default=str)[:MAX_RESULT_CHARS])

    return Tool(name=name, definition=definition(name, frozenset(ctx.bound(name))), run=run)


def tools_for(ctx: RunContext) -> list[Tool]:
    """The agent's tools from AGENT_TOOLS, bound to its run."""
    return [make_tool(name, ctx) for name in AGENT_TOOLS[ctx.agent]]
