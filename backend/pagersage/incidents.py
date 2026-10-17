"""Incident feed and detail for the UI (task B03)."""

import json

from pydantic import BaseModel, Field

from pagersage import db, graphview, queries
from pagersage.contracts.events import AgentEvent
from pagersage.contracts.schema import IncidentStatus
from pagersage.contracts.tools import IncidentReplay, ToolError, replay_incident


class IncidentSummary(BaseModel):
    id: str
    title: str
    severity: str | None
    status: str
    opened_at: int | None
    resolved_at: int | None = None
    assigned_to: str | None = Field(description="Agent name or person handle")
    alerts: int
    services: list[str] = Field(description="AFFECTED service ids (set at triage)")


class AlertOut(BaseModel):
    id: str
    service_id: str
    signal: str
    value: float
    threshold: float
    severity: str
    ts: int


class PostmortemOut(BaseModel):
    title: str
    body: str = Field(description="Markdown: What happened, Why, What fixed it, Follow-up")
    ts: int | None = None


class IncidentDetail(BaseModel):
    incident: IncidentSummary
    summary: str = ""
    postmortem: PostmortemOut | None = Field(default=None, description="After resolve (Scribe)")
    state: dict = Field(default_factory=dict, description="Shared agent scratchpad")
    alerts: list[AlertOut]
    timeline: list[AgentEvent]
    replay: IncidentReplay = Field(description="Decisions and handoffs, in order")
    graph: graphview.GraphView = Field(description="Neighbourhood and nodes to highlight")


def _summary(row) -> IncidentSummary:
    iid, title, severity, status, opened, resolved, assigned, alerts, services = row[:9]
    return IncidentSummary(
        id=iid,
        title=title or "",
        severity=severity,
        status=status or "",
        opened_at=opened,
        resolved_at=resolved,
        assigned_to=assigned,
        alerts=alerts,
        services=sorted(services),
    )


def list_incidents(status: IncidentStatus | None = None, limit: int = 50) -> list[IncidentSummary]:
    if not 1 <= limit <= 200:
        raise ToolError("limit must be between 1 and 200")
    rows = (
        db.get_graph()
        .ro_query(
            queries.load("incidents_list"),
            {"status": status.value if status else None, "limit": limit},
        )
        .result_set
    )
    return [_summary(r) for r in rows]


def incident_detail(incident_id: str) -> IncidentDetail:
    graph = db.get_graph()
    rows = graph.ro_query(queries.load("incident_detail"), {"iid": incident_id}).result_set
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    row = rows[0]
    alerts = graph.ro_query(queries.load("incident_alerts"), {"iid": incident_id}).result_set
    events = graph.ro_query(
        queries.load("incident_events"), {"iid": incident_id, "after_seq": 0}
    ).result_set
    return IncidentDetail(
        incident=_summary(row),
        summary=row[9] or "",
        state=json.loads(row[10] or "{}"),
        postmortem=PostmortemOut(**row[11]) if row[11] else None,
        alerts=[
            AlertOut(id=a, service_id=s, signal=sig, value=v, threshold=th, severity=sev, ts=ts)
            for a, s, sig, v, th, sev, ts in alerts
        ],
        timeline=[AgentEvent.from_node_props(props) for [props] in events],
        replay=replay_incident(incident_id),
        graph=graphview.incident(incident_id),
    )
