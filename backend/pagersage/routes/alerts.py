"""POST /alerts: Alertmanager-compatible webhook (task B02).

Each firing alert becomes an Alert node in a new or merged incident (open_or_merge_incident),
its `health` annotation reprices the edges into its service (update_live_weights), and a new
incident starts the orchestrator in the background (runtime.incident_opened).
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import ValidationError

from pagersage import runtime
from pagersage.contracts.ingest import AlertmanagerAlert, AlertmanagerWebhook, AlertsResult
from pagersage.contracts.schema import service_id
from pagersage.contracts.tools import (
    AlertIn,
    ToolError,
    open_or_merge_incident,
    update_live_weights,
)

router = APIRouter(tags=["alerts"])


def parse_alert(am: AlertmanagerAlert) -> tuple[AlertIn, float | None]:
    """Alertmanager alert -> (AlertIn, health or None). Raises ToolError naming what's missing."""
    labels, notes = am.labels, am.annotations
    try:
        alert = AlertIn(
            service_id=service_id(labels["service"]),
            signal=labels["signal"],
            severity=labels["severity"],
            value=float(notes["value"]),
            threshold=float(notes["threshold"]),
            ts=int(am.startsAt.timestamp()),
        )
        health = float(notes["health"]) if "health" in notes else None
    except KeyError as e:
        raise ToolError(
            f"Alert is missing {e.args[0]!r} (labels: service, signal, severity; "
            "annotations: value, threshold, health)"
        ) from e
    except (ValueError, ValidationError) as e:
        raise ToolError(f"Alert has a bad value: {e}") from e
    if health is not None and not 0.0 <= health <= 1.0:
        raise ToolError(f"health must be between 0 and 1, got {health}")
    return alert, health


@router.post("/alerts")
def post_alerts(body: AlertmanagerWebhook, background: BackgroundTasks) -> AlertsResult:
    firing = [a for a in body.alerts if a.status == "firing"]
    parsed = [parse_alert(a) for a in firing]  # all-or-nothing: check every alert first
    results = []
    for alert, health in parsed:
        result = open_or_merge_incident(alert)
        if health is not None:
            update_live_weights(alert.service_id, health)
        if not result.merged:
            background.add_task(runtime.incident_opened, result.incident_id)
        results.append(result)
    return AlertsResult(incidents=results, ignored=len(body.alerts) - len(firing))
