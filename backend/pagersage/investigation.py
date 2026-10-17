"""The Investigation screen's data (U06 suspects, U07 memory): the Investigator's and
Historian's reads rerun for one incident, so the UI can show every score, not just the pick.
Read-only; nothing here writes to the graph."""

import json

from pydantic import BaseModel, Field

from pagersage import db, queries
from pagersage.contracts import tools
from pagersage.contracts.tools import RunbookHit, SimilarIncidents, Suspect, ToolError

LOOKBACK = 2 * 3600  # suspects since the first alert minus this, as the Investigator is told


class SuspectsView(BaseModel):
    alerting_service_id: str | None = Field(description="Where the ranking starts")
    since: int
    suspects: list[Suspect] = Field(description="Highest score first, with score_parts")
    cause: str | None = Field(description="The incident's CAUSED_BY (most confident), if any")
    rejected: list[str] = Field(description="Change ids the Investigator ruled out (state)")


class MemoryView(BaseModel):
    path: list[str] = Field(description="Service ids the similar incidents are ranked against")
    similar: SimilarIncidents | None = Field(description="None until triage stores the embedding")
    runbook_service_id: str | None
    runbooks: list[RunbookHit]


def _context(incident_id: str) -> tuple[dict, list[str], int | None, list[str], list[str]]:
    rows = (
        db.get_graph()
        .ro_query(queries.load("incident_investigation"), {"iid": incident_id})
        .result_set
    )
    if not rows:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    [[state, alerting, first_alert, causes, affected]] = rows
    return json.loads(state or "{}"), sorted(alerting), first_alert, causes, sorted(affected)


def _top_of_chain(state: dict, alerting: list[str]) -> str | None:
    """The alerting service users hit: the path's start once found, else the alerting service
    with the fewest callers (checkout-api over payments-db)."""
    path = state.get("path")
    if isinstance(path, list) and path:
        return str(path[0])
    if not alerting:
        return None
    return min(alerting, key=lambda sid: (len(tools.blast_radius(sid)), sid))


def _deepest(alerting: list[str]) -> str | None:
    """Before the agents name a cause service: the alerting service with the most callers, the
    one everything else is waiting on (payments-db over checkout-api)."""
    if not alerting:
        return None
    return max(alerting, key=lambda sid: (len(tools.blast_radius(sid)), sid))


def suspects(incident_id: str) -> SuspectsView:
    state, alerting, first_alert, causes, _ = _context(incident_id)
    sid = _top_of_chain(state, alerting)
    since = (first_alert if first_alert is not None else tools._now()) - LOOKBACK
    return SuspectsView(
        alerting_service_id=sid,
        since=since,
        suspects=tools.suspect_changes(sid, since) if sid else [],
        cause=causes[0] if causes else state.get("cause"),
        rejected=[str(c) for c in state.get("rejected", [])],
    )


def memory(incident_id: str) -> MemoryView:
    state, alerting, _, _, affected = _context(incident_id)
    path = state.get("path")
    path = [str(s) for s in path] if isinstance(path, list) and path else affected or alerting
    try:
        similar = tools.similar_incidents(incident_id, path)
    except ToolError:  # not triaged yet: no embedding to search from
        similar = None
    cause_service = state.get("cause_service") or _deepest(alerting)
    return MemoryView(
        path=path,
        similar=similar,
        runbook_service_id=cause_service,
        runbooks=tools.best_runbook(cause_service) if cause_service else [],
    )
