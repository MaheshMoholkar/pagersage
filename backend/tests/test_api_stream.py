"""GET /incidents/{id}/events (B04): SSE replay from Last-Event-ID, then live events."""

import asyncio
import json

import pytest

from pagersage import stream
from pagersage.contracts import tools
from pagersage.contracts.events import EventKind
from tests.test_api_alerts import payload

T0 = 1_792_800_000


@pytest.fixture(scope="module")
def live(write_graph):
    """A live incident with three events: two alerts and a finding."""
    from fastapi.testclient import TestClient

    from pagersage import db, runtime
    from pagersage.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(db, "get_graph", lambda name=None: write_graph)
        mp.setattr(runtime, "_opened", [])
        client = TestClient(app)
        r = client.post("/alerts", json=payload("payments-db", ts=T0)).json()
        client.post(
            "/alerts", json=payload("checkout-api", "error_rate", "sev1", 8.4, 1.0, ts=T0 + 20)
        )
        iid = r["incidents"][0]["incident_id"]
        tools.append_event(iid, EventKind.FINDING, "payments-db is the bottom of it", ts=T0 + 30)
    return iid


def _messages(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        fields = dict(line.split(": ", 1) for line in lines)
        data = json.loads(fields["data"])
        out.append({"id": int(fields["id"]), "event": fields["event"], **data})
    return out


def test_replays_the_whole_timeline_as_sse(api, writer, live):
    r = api.get(f"/incidents/{live}/events", params={"follow": "false"})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    msgs = _messages(r.text)
    assert [(m["id"], m["event"], m["kind"]) for m in msgs] == [
        (1, "agent", "status"),
        (2, "agent", "status"),
        (3, "agent", "finding"),
    ]
    assert msgs[2]["summary"] == "payments-db is the bottom of it"


def test_resumes_after_last_event_id(api, writer, live):
    r = api.get(
        f"/incidents/{live}/events", params={"follow": "false"}, headers={"Last-Event-ID": "2"}
    )

    assert [m["id"] for m in _messages(r.text)] == [3]


def test_streams_new_events_as_they_land(writer, live):
    async def run():
        gen = stream.event_stream(live, after_seq=3, poll=0.05)
        nxt = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.15)
        assert not nxt.done()  # nothing new yet
        await asyncio.to_thread(tools.append_event, live, EventKind.ACTION, "paged priya", T0 + 60)
        msg = await asyncio.wait_for(nxt, 2)
        await gen.aclose()
        return msg

    msg = asyncio.run(run())
    assert msg.startswith("id: 4\nevent: agent\n") and '"paged priya"' in msg


def test_sends_keepalives_while_quiet(writer, live, monkeypatch):
    monkeypatch.setattr(stream, "KEEPALIVE_SECONDS", 0.1)

    async def run():
        gen = stream.event_stream(live, after_seq=999, poll=0.05)
        msg = await asyncio.wait_for(gen.__anext__(), 2)
        await gen.aclose()
        return msg

    assert asyncio.run(run()) == ": keepalive\n\n"


def test_stops_when_the_client_disconnects(writer, live):
    async def gone() -> bool:
        return True

    async def run():
        return [m async for m in stream.event_stream(live, after_seq=999, disconnected=gone)]

    assert asyncio.run(run()) == []


def test_unknown_incident_is_a_400(api, writer):
    assert api.get("/incidents/INC-999/events").status_code == 400
