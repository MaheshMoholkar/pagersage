"""GET /incidents and /incidents/{id} (B03)."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from tests.test_api_alerts import payload

T0 = 1_792_700_000


@pytest.fixture(scope="module")
def live(write_graph):
    """One live incident from two related alerts, a handoff and a decision."""
    from fastapi.testclient import TestClient

    from pagersage import db, runtime
    from pagersage.main import app

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(db, "get_graph", lambda name=None: write_graph)
        mp.setattr(runtime, "_opened", [])
        mp.setattr(tools, "_now", lambda: T0 + 120)
        client = TestClient(app)
        first = client.post("/alerts", json=payload("payments-db", health=0.15, ts=T0)).json()
        client.post(
            "/alerts",
            json=payload("checkout-api", "error_rate", "sev1", 8.4, 1.0, health=0.4, ts=T0 + 20),
        )
        iid = first["incidents"][0]["incident_id"]
        tools.handoff(
            iid,
            AgentName.TRIAGE,
            AgentName.INVESTIGATOR,
            "payments-db is sick",
            {"alerting_service": "svc:checkout-api"},
        )
        tools.record_decision(
            iid, AgentName.INVESTIGATOR, "pool cut is the cause", "top suspect", 0.8, ["cfg-0050"]
        )
    return iid


def test_feed_lists_newest_first_with_status_and_severity(api, writer, live):
    feed = api.get("/incidents", params={"limit": 5}).json()

    assert feed[0]["id"] == live
    top = feed[0]
    assert (top["status"], top["severity"], top["alerts"], top["assigned_to"]) == (
        "open",
        "sev1",
        2,
        "investigator",
    )
    opened = [i["opened_at"] for i in feed]
    assert opened == sorted(opened, reverse=True)


def test_feed_filters_by_status(api, writer, live):
    open_ids = [i["id"] for i in api.get("/incidents", params={"status": "open"}).json()]
    resolved = api.get("/incidents", params={"status": "resolved", "limit": 200}).json()

    assert live in open_ids
    assert len(resolved) == 40 and all(i["status"] == "resolved" for i in resolved)


def test_detail_has_alerts_timeline_trace_and_graph(api, writer, live):
    d = api.get(f"/incidents/{live}").json()

    assert d["incident"]["id"] == live
    assert d["state"] == {"alerting_service": "svc:checkout-api"}
    assert [a["service_id"] for a in d["alerts"]] == ["svc:payments-db", "svc:checkout-api"]
    assert [e["kind"] for e in d["timeline"]] == ["status", "status", "handoff"]
    assert [e["seq"] for e in d["timeline"]] == [1, 2, 3]
    assert [x["what"] for x in d["replay"]["decisions"]] == ["pool cut is the cause"]
    assert [h["to_agent"] for h in d["replay"]["handoffs"]] == ["investigator"]
    nodes = {n["id"] for n in d["graph"]["nodes"]}
    assert {"svc:payments-db", "svc:checkout-api"} <= nodes
    assert "svc:payments-db" in d["graph"]["highlight"]["nodes"]


def test_past_incidents_have_details_too(api, tool_graph):
    d = api.get("/incidents/INC-042").json()

    assert d["incident"]["status"] == "resolved"
    assert d["incident"]["services"] == ["svc:checkout-api", "svc:payments-db", "svc:payments-svc"]
    assert len(d["timeline"]) >= 3 and d["timeline"][0]["seq"] == 1


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        ("/incidents/INC-999", {}, 400),
        ("/incidents", {"status": "sleepy"}, 422),
        ("/incidents", {"limit": 0}, 400),
    ],
)
def test_bad_requests(api, tool_graph, path, params, status):
    assert api.get(path, params=params).status_code == status
