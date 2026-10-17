"""Hooks between the API and the orchestrator (task A03), so the routes can be built and tested
before the agents exist. The orchestrator registers callbacks at import; until then nothing
listens and incidents simply wait in the graph.

    @runtime.on_incident_opened
    def start(incident_id: str) -> None: ...
"""

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)
Hook = Callable[[str], None]

_opened: list[Hook] = []
_resolved: list[Hook] = []


def on_incident_opened(fn: Hook) -> Hook:
    """Run fn(incident_id) in the background when an alert opens a new incident (B02)."""
    _opened.append(fn)
    return fn


def on_incident_resolved(fn: Hook) -> Hook:
    """Run fn(incident_id) in the background when an incident is resolved (B09; Scribe)."""
    _resolved.append(fn)
    return fn


def _fire(hooks: list[Hook], incident_id: str) -> None:
    for fn in list(hooks):
        try:
            fn(incident_id)
        except Exception:  # a broken listener must not break the webhook
            log.exception("hook %s failed for %s", getattr(fn, "__name__", fn), incident_id)


def incident_opened(incident_id: str) -> None:
    _fire(_opened, incident_id)


def incident_resolved(incident_id: str) -> None:
    _fire(_resolved, incident_id)
