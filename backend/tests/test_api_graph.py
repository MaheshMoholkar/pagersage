"""GET /graph (B06): company view and an incident's neighbourhood with its highlight."""

from pagersage.contracts import tools
from pagersage.contracts.events import EventKind, Highlight
from tests.test_api_alerts import payload


def test_company_view_has_every_service_and_dependency(api, tool_graph):
    view = api.get("/graph").json()

    services = {n["id"]: n for n in view["nodes"]}
    assert len(services) == 26 and len(view["links"]) == 42
    kafka = services["svc:kafka"]
    assert (kafka["team"], kafka["kind"], kafka["health"]) == ("Platform", "Service", 1.0)
    assert kafka["fragility"] == max(n["fragility"] for n in view["nodes"])
    link = next(
        lk
        for lk in view["links"]
        if lk["source"] == "svc:payments-svc" and lk["target"] == "svc:payments-db"
    )
    assert (link["type"], link["weight"]) == ("DEPENDS_ON", 100)
    assert view["highlight"] == {"nodes": [], "edges": []}


def test_incident_view_shows_its_services_alerts_and_highlight(api, writer):
    t0 = 1_792_600_000
    inc = api.post("/alerts", json=payload("payments-db", health=0.15, ts=t0)).json()
    iid, aid = inc["incidents"][0]["incident_id"], inc["incidents"][0]["alert_id"]
    # what the Investigator's root_cause_path event will carry (A11)
    tools.append_event(
        iid,
        EventKind.FINDING,
        "pool cut on payments-db",
        ts=t0 + 60,
        highlight=Highlight(
            nodes=[
                "svc:checkout-api",
                "svc:payments-svc",
                "svc:payments-db",
                "cfg-0050",
                "person:tomas",
            ],
            edges=[
                ("svc:checkout-api", "DEPENDS_ON", "svc:payments-svc"),
                ("svc:payments-svc", "DEPENDS_ON", "svc:payments-db"),
                ("cfg-0050", "CHANGED", "svc:payments-db"),
                ("person:tomas", "MADE", "cfg-0050"),
            ],
        ),
    )

    view = api.get("/graph", params={"incident": iid}).json()

    kinds = {n["id"]: n["kind"] for n in view["nodes"]}
    # payments-db, its neighbours (payments-svc, reconciliation-job...), the path's checkout-api
    assert {"svc:payments-db", "svc:payments-svc", "svc:checkout-api"} <= kinds.keys()
    assert (kinds[aid], kinds["cfg-0050"], kinds["person:tomas"]) == (
        "Alert",
        "ConfigChange",
        "Person",
    )
    links = {(lk["source"], lk["type"], lk["target"]) for lk in view["links"]}
    assert (aid, "FIRED_ON", "svc:payments-db") in links
    assert ("cfg-0050", "CHANGED", "svc:payments-db") in links
    assert ("person:tomas", "MADE", "cfg-0050") in links
    assert "cfg-0050" in view["highlight"]["nodes"]
    assert ["svc:payments-svc", "DEPENDS_ON", "svc:payments-db"] in view["highlight"]["edges"]
    ids = [n["id"] for n in view["nodes"]]
    assert len(ids) == len(set(ids))
    sick = next(n for n in view["nodes"] if n["id"] == "svc:payments-db")
    assert sick["health"] == 0.15


def test_unknown_incident_is_a_400(api, writer):
    assert api.get("/graph", params={"incident": "INC-999"}).status_code == 400
