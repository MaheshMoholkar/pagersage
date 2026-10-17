"""GET /incidents, /incidents/{id} (task B03), the SSE stream /incidents/{id}/events (B04),
the Investigation screen's /incidents/{id}/suspects and /memory (U06, U07), and the UI's action
card: POST /incidents/{id}/rollback and /incidents/{id}/resolve (B09)."""

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pagersage import incidents, investigation, runtime, stream
from pagersage.contracts import tools
from pagersage.contracts.schema import IncidentStatus
from pagersage.contracts.tools import ActionResult
from pagersage.incidents import IncidentDetail, IncidentSummary

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("")
def list_incidents(status: IncidentStatus | None = None, limit: int = 50) -> list[IncidentSummary]:
    """The incident feed, newest first; ?status=open for live ones only."""
    return incidents.list_incidents(status, limit)


@router.get("/{incident_id}")
def get_incident(incident_id: str) -> IncidentDetail:
    """One incident: alerts, timeline, decisions, handoffs, and its graph neighbourhood."""
    return incidents.incident_detail(incident_id)


@router.get("/{incident_id}/suspects")
def get_suspects(incident_id: str) -> investigation.SuspectsView:
    """Every suspect change with its score breakdown, from the top-of-chain alerting service."""
    return investigation.suspects(incident_id)


@router.get("/{incident_id}/memory")
def get_memory(incident_id: str) -> investigation.MemoryView:
    """Similar past incidents (vector-only and graph re-ranked) and the cause service's runbooks."""
    return investigation.memory(incident_id)


@router.get("/{incident_id}/events")
def stream_events(
    incident_id: str,
    request: Request,
    after: int = 0,
    follow: bool = True,
    last_event_id: int | None = Header(default=None),
) -> StreamingResponse:
    """The incident's timeline as Server-Sent Events: replays events after Last-Event-ID (or
    ?after=), then streams new ones live. ?follow=false replays and closes."""
    stream.check_incident(incident_id)
    return StreamingResponse(
        stream.event_stream(
            incident_id,
            after_seq=last_event_id if last_event_id is not None else after,
            follow=follow,
            disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RollbackIn(BaseModel):
    service_id: str
    deploy_id: str


class RevertIn(BaseModel):
    change_id: str = Field(min_length=1, description="dep-.... or cfg-.... (the cause)")


class ResolveIn(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)


@router.post("/{incident_id}/rollback")
def post_rollback(incident_id: str, body: RollbackIn) -> ActionResult:
    """A person approved the Responder's rollback (simulated); logged on the timeline."""
    stream.check_incident(incident_id)
    result = tools.rollback(body.service_id, body.deploy_id)
    tools.append_event(
        incident_id,
        tools.EventKind.ACTION,
        result.detail,
        data={"action": result.action.value, "ok": result.ok, "deploy_id": body.deploy_id},
    )
    return result


@router.post("/{incident_id}/revert")
def post_revert(incident_id: str, body: RevertIn) -> ActionResult:
    """A person reverted the cause, deploy or config change (simulated); incident mitigated."""
    return tools.revert_change(incident_id, body.change_id)


@router.post("/{incident_id}/resolve")
def post_resolve(incident_id: str, body: ResolveIn, background: BackgroundTasks) -> dict:
    """Resolve the incident; the Scribe (A08) writes the postmortem in the background."""
    tools.resolve_incident(incident_id, body.summary)
    background.add_task(runtime.incident_resolved, incident_id)
    return {"incident_id": incident_id, "status": "resolved"}
