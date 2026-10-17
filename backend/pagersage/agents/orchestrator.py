"""Orchestrator (task A03): a plain state machine over the agents, no framework.

    alert opens an incident ─► Triage ─► Investigator ─► Historian ─► Responder
    a person resolves it    ─► Scribe

Each agent starts from the incident as the graph holds it (`brief`): alerts, triage, the
shared state and the handoff note addressed to it. It never sees another agent's transcript,
so the graph is the only channel between agents and every step can be replayed from it.
Pipeline agents finish by calling handoff; the Scribe finishes with write_postmortem.
Anything else (a refusal, the tool-call cap, a timeout, no handoff, an API error) stops the
pipeline and marks the incident needs_human.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pagersage import incidents, runtime
from pagersage.agents import emitter, llm, prompts, registry
from pagersage.config import get_settings
from pagersage.contracts import tools
from pagersage.contracts.events import EventKind
from pagersage.contracts.schema import AgentName

log = logging.getLogger(__name__)

PIPELINE = (AgentName.TRIAGE, AgentName.INVESTIGATOR, AgentName.HISTORIAN, AgentName.RESPONDER)
NEXT = {
    AgentName.TRIAGE: AgentName.INVESTIGATOR,
    AgentName.INVESTIGATOR: AgentName.HISTORIAN,
    AgentName.HISTORIAN: AgentName.RESPONDER,
    AgentName.RESPONDER: AgentName.SCRIBE,
}
FINISH = {AgentName.SCRIBE: "write_postmortem"}  # everyone else: handoff
WHY = {
    "refusal": "the model declined to continue",
    "tool_cap": f"it hit the {llm.MAX_TOOL_CALLS}-tool-call cap",
    "timeout": f"it ran past {llm.TIMEOUT:.0f} s",
    "max_tokens": "its reply ran out of tokens",
    "no_finish": "it stopped without handing off",
}


def _when(ts: int | None) -> str:
    if ts is None:
        return "unknown"
    return f"{datetime.fromtimestamp(ts, UTC):%Y-%m-%d %H:%M:%S} UTC (epoch {ts})"


def brief(incident_id: str, agent: AgentName) -> str:
    """The incident as the graph holds it now: what the agent starts from."""
    d = incidents.incident_detail(incident_id)
    inc = d.incident
    lines = [
        f"Incident {inc.id} [{inc.severity}] status {inc.status}, opened {_when(inc.opened_at)}",
        f"Title: {inc.title}",
    ]
    if d.summary:
        lines.append(f"Summary: {d.summary}")
    lines.append("Alerts:")
    lines += [
        f"- {a.id}: {a.service_id} {a.signal} {a.value:g} (threshold {a.threshold:g}, "
        f"{a.severity}) at {a.ts}"
        for a in d.alerts
    ]
    if inc.services:
        lines.append(f"Affected services (triage): {', '.join(inc.services)}")
    if d.state:
        lines.append(f"Shared state from earlier agents: {json.dumps(d.state, sort_keys=True)}")
    notes = [h for h in d.replay.handoffs if h.to_agent == agent.value]
    if notes:
        lines.append(f"Handoff note from {notes[-1].from_agent}: {notes[-1].note}")
    body = "\n".join(lines).replace("<", "&lt;").replace(">", "&gt;")  # text can't close the fence
    return (
        f"<incident>\n{body}\n</incident>\nDo your job for {inc.id} now, as your instructions say."
    )


def run_agent(agent: AgentName, incident_id: str, api: Any = None) -> llm.RunResult:
    ctx = registry.RunContext(agent, incident_id, NEXT.get(agent), on_call=emitter.on_call)
    tools.append_event(incident_id, EventKind.STATUS, f"{agent.value} started", agent=agent)
    return llm.run(
        agent,
        prompts.system(agent),
        brief(incident_id, agent),
        registry.tools_for(ctx),
        finish={FINISH.get(agent, "handoff")},
        api=api,
    )


def _step(agent: AgentName, incident_id: str, api: Any) -> bool:
    """Run one agent; on anything but a clean finish mark the incident needs_human."""
    try:
        result = run_agent(agent, incident_id, api)
    except Exception as e:  # API down, no key, graph error: a person takes over
        log.exception("%s failed on %s", agent.value, incident_id)
        tools.mark_needs_human(incident_id, f"{agent.value} failed: {type(e).__name__}: {e}")
        return False
    if not result.ok:
        tools.mark_needs_human(incident_id, f"{agent.value} stopped: {WHY[result.stop]}")
        return False
    return True


def run_pipeline(incident_id: str, api: Any = None) -> bool:
    """Triage → Investigator → Historian → Responder. True when every agent handed off."""
    return all(_step(agent, incident_id, api) for agent in PIPELINE)


def run_scribe(incident_id: str, api: Any = None) -> bool:
    return _step(AgentName.SCRIBE, incident_id, api)


_installed = False


def install() -> bool:
    """Start the agents on runtime hooks: new incident → pipeline, resolved → Scribe.
    Does nothing when AGENTS_ENABLED is false or there is no ANTHROPIC_API_KEY."""
    global _installed
    settings = get_settings()
    if _installed or not settings.agents_enabled:
        return _installed
    if not settings.anthropic_api_key:
        log.warning("Agents off: ANTHROPIC_API_KEY is not set; incidents wait in the graph")
        return False
    runtime.on_incident_opened(run_pipeline)
    runtime.on_incident_resolved(run_scribe)
    _installed = True
    return True
