"""Live incident timeline over Server-Sent Events (task B04).

Events live in the graph (Event nodes, written by alerts, handoffs and the A11 emitter), so the
stream tails the graph: replay everything after the client's last seq, then poll for newer
ones. That works across processes and survives API restarts: a reconnecting EventSource sends
Last-Event-ID (= seq) and picks up exactly where it stopped.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from pagersage import db, queries
from pagersage.contracts.events import AgentEvent
from pagersage.contracts.tools import ToolError

POLL_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0


def _events_after(incident_id: str, after_seq: int) -> list[AgentEvent]:
    rows = (
        db.get_graph()
        .ro_query(queries.load("incident_events"), {"iid": incident_id, "after_seq": after_seq})
        .result_set
    )
    return [AgentEvent.from_node_props(props) for [props] in rows]


def check_incident(incident_id: str) -> None:
    if (
        not db.get_graph()
        .ro_query(queries.load("incident_last_seq"), {"iid": incident_id})
        .result_set
    ):
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")


async def event_stream(
    incident_id: str,
    after_seq: int = 0,
    follow: bool = True,
    disconnected: Callable[[], Awaitable[bool]] | None = None,
    poll: float = POLL_SECONDS,
) -> AsyncIterator[str]:
    """SSE messages for the incident's events with seq > after_seq, then (follow) new ones as
    they land. Sends a comment line every KEEPALIVE_SECONDS so proxies keep the line open."""
    last, idle = after_seq, 0.0
    while True:
        events = await asyncio.to_thread(_events_after, incident_id, last)
        for event in events:
            last = event.seq
            yield event.to_sse()
        if not follow:
            return
        if disconnected and await disconnected():
            return
        if events:
            idle = 0.0
        elif (idle := idle + poll) >= KEEPALIVE_SECONDS:
            idle = 0.0
            yield ": keepalive\n\n"
        await asyncio.sleep(poll)
