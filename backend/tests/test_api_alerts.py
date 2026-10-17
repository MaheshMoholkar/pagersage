"""POST /alerts (B02): Alertmanager JSON -> Alert nodes, merged or new incidents, live weights,
the orchestrator hook. Each test uses its own time window so tests don't merge into each other."""

import itertools
from datetime import UTC, datetime

import pytest

from pagersage import runtime

_windows = itertools.count(1)


def _at(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def payload(
    service,
    signal="saturation",
    severity="sev2",
    value=0.99,
    threshold=0.9,
    health=None,
    ts=0,
    status="firing",
    **labels,
):
    notes = {"value": str(value), "threshold": str(threshold)}
    if health is not None:
        notes["health"] = str(health)
    alert = {
        "status": status,
        "labels": {"alertname": "X", "service": service, "signal": signal, "severity": severity}
        | labels,
        "annotations": notes,
        "startsAt": _at(ts),
        "endsAt": "0001-01-01T00:00:00Z",
        "fingerprint": "f",
    }
    return {"version": "4", "status": status, "receiver": "pagersage", "alerts": [alert]}


@pytest.fixture
def t0():
    """A fresh hour per test, after Kestrel Pay's history."""
    return 1_792_500_000 + next(_windows) * 3600


@pytest.fixture
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "_opened", [calls.append])
    return calls


def _incident(g, iid):
    return g.ro_query(
        "MATCH (i:Incident {id:$iid}) RETURN i.status, i.severity, i.title, "
        "[(a:Alert)-[:PART_OF]->(i) | a.id]",
        {"iid": iid},
    ).result_set[0]


def test_first_alert_opens_an_incident(api, writer, opened, t0):
    r = api.post("/alerts", json=payload("payments-db", health=0.15, ts=t0))

    assert r.status_code == 200
    [res] = r.json()["incidents"]
    assert res["merged"] is False
    status, severity, title, alerts = _incident(writer, res["incident_id"])
    assert (status, severity, alerts) == ("open", "sev2", [res["alert_id"]])
    assert title == "payments-db saturation 0.99 (threshold 0.9)"
    assert writer.ro_query(
        "MATCH (a:Alert {id:$aid})-[:FIRED_ON]->(s:Service) RETURN s.id, a.signal, a.value, a.ts",
        {"aid": res["alert_id"]},
    ).result_set == [["svc:payments-db", "saturation", 0.99, t0]]
    assert opened == [res["incident_id"]]  # the orchestrator is started once


def test_health_reprices_the_edges_into_the_service(api, writer, opened, t0):
    api.post("/alerts", json=payload("payments-db", health=0.15, ts=t0))

    assert writer.ro_query(
        "MATCH ()-[d:DEPENDS_ON]->(s:Service {id:'svc:payments-db'}) "
        "RETURN collect(DISTINCT d.weight), s.health"
    ).result_set == [[[15], 0.15]]


def test_a_related_alert_soon_after_joins_the_incident(api, writer, opened, t0):
    # The scenario: payments-db saturates, checkout-api (two hops up) errors 20 s later.
    first = api.post("/alerts", json=payload("payments-db", ts=t0)).json()["incidents"][0]
    second = api.post(
        "/alerts",
        json=payload("checkout-api", "error_rate", "sev1", 8.4, 1.0, health=0.4, ts=t0 + 20),
    ).json()["incidents"][0]

    assert (second["incident_id"], second["merged"]) == (first["incident_id"], True)
    _, severity, _, alerts = _incident(writer, first["incident_id"])
    assert severity == "sev1"  # raised to the worst alert
    assert sorted(alerts) == sorted([first["alert_id"], second["alert_id"]])
    assert opened == [first["incident_id"]]
    events = writer.ro_query(
        "MATCH (e:Event)-[:PART_OF]->(:Incident {id:$iid}) RETURN e.seq, e.kind ORDER BY e.seq",
        {"iid": first["incident_id"]},
    ).result_set
    assert events == [[1, "status"], [2, "status"]]
    assert writer.ro_query(
        "MATCH (a:Event)-[:NEXT]->(b:Event)-[:PART_OF]->(:Incident {id:$iid}) RETURN a.seq, b.seq",
        {"iid": first["incident_id"]},
    ).result_set == [[1, 2]]


def test_unrelated_or_late_alerts_open_new_incidents(api, writer, opened, t0):
    first = api.post("/alerts", json=payload("payments-db", ts=t0)).json()["incidents"][0]
    unrelated = api.post("/alerts", json=payload("search-index", ts=t0 + 30)).json()
    late = api.post("/alerts", json=payload("payments-db", ts=t0 + 700)).json()

    ids = {first["incident_id"], unrelated["incidents"][0]["incident_id"]}
    ids.add(late["incidents"][0]["incident_id"])
    assert len(ids) == 3
    assert not unrelated["incidents"][0]["merged"] and not late["incidents"][0]["merged"]


def test_a_resolved_incident_is_not_reopened(api, writer, opened, t0):
    first = api.post("/alerts", json=payload("payments-db", ts=t0)).json()["incidents"][0]
    writer.query(
        "MATCH (i:Incident {id:$iid}) SET i.status = 'resolved'", {"iid": first["incident_id"]}
    )

    again = api.post("/alerts", json=payload("payments-db", ts=t0 + 60)).json()["incidents"][0]

    assert again["incident_id"] != first["incident_id"]


def test_ids_continue_the_history(api, writer, opened, t0):
    res = api.post("/alerts", json=payload("payments-db", ts=t0)).json()["incidents"][0]

    assert res["incident_id"] > "INC-050" and res["alert_id"] > "alt-00060"


def test_resolved_alerts_are_ignored(api, writer, opened, t0):
    r = api.post("/alerts", json=payload("payments-db", ts=t0, status="resolved"))

    assert r.json() == {"incidents": [], "ignored": 1}
    assert opened == []


@pytest.mark.parametrize(
    "kw",
    [
        {"service": "nope-svc"},  # unknown service
        {"service": "payments-db", "signal": "vibes"},  # not a signal
        {"service": "payments-db", "health": 1.5},
    ],
)
def test_bad_alerts_are_400s_and_write_nothing(api, writer, opened, t0, kw):
    before = writer.ro_query("MATCH (a:Alert) RETURN count(a)").result_set

    r = api.post("/alerts", json=payload(ts=t0, **kw))

    assert r.status_code == 400, r.text
    assert writer.ro_query("MATCH (a:Alert) RETURN count(a)").result_set == before


def test_missing_labels_are_400s(api, writer, opened, t0):
    body = payload("payments-db", ts=t0)
    del body["alerts"][0]["labels"]["service"]

    r = api.post("/alerts", json=body)

    assert r.status_code == 400 and "service" in r.json()["error"]
