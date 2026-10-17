"""Agent event emitter (task A11): every tool call lands on the incident timeline.

The registry hands each finished call to `on_call` (RunContext.on_call). Events are written
with tools.append_event, so they become Event nodes and stream over SSE (B04) like the rest.

    read tool                    tool_call {tool, input, ok, rows}, highlighting what it found
    set_triage, record_cause,    finding {tool, input}
    link_similar, write_postmortem, record_runbook_outcome
    record_decision              decision {decision_id, confidence, what}
    rollback                     action {action, ok, url} (page_owner and open_issue log their own)
    handoff                      nothing: the handoff tool writes its own handoff event
    any failed call              error {tool, input, hint}
"""

import logging
from typing import Any

from pydantic import BaseModel

from pagersage.agents.registry import ToolCall
from pagersage.contracts import tools
from pagersage.contracts.events import EventKind, Highlight
from pagersage.contracts.schema import Rel, person_id

log = logging.getLogger(__name__)

SELF_LOGGING = {"handoff", "page_owner", "open_issue"}
FINDINGS = {
    "set_triage",
    "record_cause",
    "link_similar",
    "write_postmortem",
    "record_runbook_outcome",
}


def _args(input: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in input.items() if not isinstance(v, list | dict))[:80]


def _label(v: Any) -> str:
    if isinstance(v, tools.Suspect):
        return f"{v.change_id} ({v.score:.2f})"
    if isinstance(v, tools.PageTarget | tools.Expert):
        return v.handle
    if isinstance(v, tools.BusFactorRisk):
        return f"{v.service_id} ({v.sole_author})"
    return getattr(v, "id", None) or str(v)


def _nodes(value: Any) -> list[str]:
    if isinstance(value, tools.SimilarIncidents):
        return [i.id for i in value.graph_ranked]
    if not isinstance(value, list):
        return []
    nodes: list[str] = []
    for v in value[:5]:
        if isinstance(v, tools.Suspect):
            nodes += [v.change_id, v.service_id]
        elif isinstance(v, tools.PageTarget | tools.Expert):
            nodes.append(person_id(v.handle))
        elif isinstance(v, tools.BusFactorRisk):
            nodes.append(v.service_id)
        elif isinstance(v, BaseModel) and hasattr(v, "id"):
            nodes.append(v.id)
    return list(dict.fromkeys(nodes))


def _read_event(call: ToolCall) -> tuple[str, Highlight]:
    v = call.value
    if isinstance(v, tools.RootCausePath):
        names = " → ".join(s.removeprefix("svc:") for s in v.services)
        return f"Root-cause path {names} → {v.change_id} (weight {v.path_weight})", v.highlight
    if isinstance(v, tools.SimilarIncidents):
        graph_ids = ", ".join(i.id for i in v.graph_ranked)
        vector_ids = ", ".join(i.id for i in v.vector_only)
        return f"Similar incidents {graph_ids} (vector only: {vector_ids})", Highlight(
            nodes=_nodes(v)
        )
    items = v if isinstance(v, list) else [v]
    head = ", ".join(_label(x) for x in items[:3])
    return f"{call.tool}({_args(call.input)}): {len(items)} found. {head}", Highlight(
        nodes=_nodes(v)
    )


def _finding_highlight(call: ToolCall) -> Highlight:
    i, iid = call.input, call.incident_id or ""
    if call.tool == "record_cause":
        return Highlight(nodes=[i["change_id"]], edges=[(iid, Rel.CAUSED_BY, i["change_id"])])
    if call.tool == "link_similar":
        other = i["other_incident_id"]
        return Highlight(nodes=[other], edges=[(iid, Rel.SIMILAR_TO, other)])
    if call.tool == "set_triage":
        return Highlight(nodes=list(i.get("impacted_service_ids", [])))
    if call.tool == "record_runbook_outcome":
        return Highlight(nodes=[i["runbook_id"]], edges=[(i["runbook_id"], Rel.RESOLVED, iid)])
    return Highlight()


def event_for(call: ToolCall) -> tuple[EventKind, str, dict[str, Any], Highlight] | None:
    """(kind, summary, data, highlight) for one call, or None when the tool logs itself."""
    if call.error is not None and call.value is None:
        data = {"tool": call.tool, "input": call.input, "hint": call.error}
        return EventKind.ERROR, f"{call.tool} failed: {call.error}", data, Highlight()
    if call.tool in SELF_LOGGING:
        return None
    if call.tool == "record_decision":
        i = call.input
        data = {"decision_id": call.value, "confidence": i.get("confidence"), "what": i.get("what")}
        evidence = list(i.get("evidence_ids", []))
        return EventKind.DECISION, f"Decided: {i.get('what', '')}", data, Highlight(nodes=evidence)
    if call.tool == "rollback":
        r: tools.ActionResult = call.value
        data = {"action": r.action.value, "ok": r.ok, "url": r.url, "input": call.input}
        return EventKind.ACTION, r.detail, data, Highlight(nodes=[call.input.get("deploy_id", "")])
    if call.tool in FINDINGS:
        what = call.input.get("title") or call.input.get("change_id") or _args(call.input)
        data = {"tool": call.tool, "input": call.input}
        return EventKind.FINDING, f"{call.tool}: {what}", data, _finding_highlight(call)
    summary, highlight = _read_event(call)
    rows = len(call.value) if isinstance(call.value, list) else 1
    data = {"tool": call.tool, "input": call.input, "ok": call.error is None, "rows": rows}
    if call.error:
        data["hint"] = call.error
    return EventKind.TOOL_CALL, summary, data, highlight


def on_call(call: ToolCall) -> None:
    """RunContext.on_call: append the call's event. Never raises; a lost event is logged."""
    if call.incident_id is None:  # Brain answers questions; there is no timeline
        return
    try:
        if (event := event_for(call)) is None:
            return
        kind, summary, data, highlight = event
        tools.append_event(
            call.incident_id, kind, summary, agent=call.agent, data=data, highlight=highlight
        )
    except Exception:
        log.exception("could not log %s for %s", call.tool, call.incident_id)
