"""Simulated rollback and resolve (B09), as tools and as the UI's action-card routes."""

import pytest

from pagersage import runtime
from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError
from tests.test_action_page import incident  # noqa: F401 (fixture)


def _latest_ok_deploy(g, sid):
    return g.ro_query(
        "MATCH (d:Deploy {status:'ok'})-[:TARGETED]->(:Service {id:$sid}) "
        "WHERE d.simulated IS NULL RETURN d.id, d.version ORDER BY d.ts DESC LIMIT 2",
        {"sid": sid},
    ).result_set


def test_rollback_marks_the_deploy_and_redeploys_the_previous_version(writer):
    (bad, bad_version), (_, previous) = _latest_ok_deploy(writer, "svc:search-api")

    r = tools.rollback("svc:search-api", bad)

    assert (r.ok, r.action) == (True, "rollback")
    assert previous in r.detail and "Simulated" in r.detail
    q = "MATCH (d:Deploy {id:$id}) RETURN d.status"
    [[status]] = writer.ro_query(q, {"id": bad}).result_set
    assert status == "rolled_back"
    [[new_id, version, new_status, simulated]] = writer.ro_query(
        "MATCH (n:Deploy)-[:ROLLED_BACK]->(:Deploy {id:$id}), (n)-[:TARGETED]->(:Service "
        "{id:'svc:search-api'}) RETURN n.id, n.version, n.status, n.simulated",
        {"id": bad},
    ).result_set
    assert (version, new_status, simulated) == (previous, "ok", True)
    assert new_id > "dep-0415" and version != bad_version


@pytest.mark.parametrize(
    ("sid", "did"),
    [
        ("svc:search-api", "dep-9999"),  # unknown deploy
        ("svc:payments-db", "dep-0001"),  # dep-0001 shipped search-api
        ("svc:nope", "dep-0001"),
    ],
)
def test_bad_rollbacks_are_tool_errors(writer, sid, did):
    with pytest.raises(ToolError):
        tools.rollback(sid, did)


def test_a_deploy_is_rolled_back_only_once(writer):
    [(bad, _), _] = _latest_ok_deploy(writer, "svc:user-api")
    tools.rollback("svc:user-api", bad)

    with pytest.raises(ToolError, match="already"):
        tools.rollback("svc:user-api", bad)


def test_rollback_route_logs_the_action_on_the_incident(api, writer, incident):  # noqa: F811
    [(bad, _), _] = _latest_ok_deploy(writer, "svc:payments-svc")

    r = api.post(
        f"/incidents/{incident}/rollback", json={"service_id": "svc:payments-svc", "deploy_id": bad}
    )

    assert r.status_code == 200 and r.json()["ok"] is True
    [[kind, text]] = writer.ro_query(
        "MATCH (e:Event)-[:PART_OF]->(:Incident {id:$iid}) RETURN e.kind, e.text "
        "ORDER BY e.seq DESC LIMIT 1",
        {"iid": incident},
    ).result_set
    assert kind == "action" and "Simulated rollback" in text


def test_resolve_closes_heals_and_starts_the_scribe(api, writer, incident, monkeypatch):  # noqa: F811
    scribe = []
    monkeypatch.setattr(runtime, "_resolved", [scribe.append])
    tools.update_live_weights("svc:payments-db", 0.15)

    r = api.post(f"/incidents/{incident}/resolve", json={"summary": "Raised the pool."})

    assert r.status_code == 200
    [[status, resolved_at, summary]] = writer.ro_query(
        "MATCH (i:Incident {id:$iid}) RETURN i.status, i.resolved_at, i.summary",
        {"iid": incident},
    ).result_set
    assert (status, summary) == ("resolved", "Raised the pool.") and resolved_at > 0
    assert writer.ro_query(
        "MATCH ()-[d:DEPENDS_ON]->(s:Service {id:'svc:payments-db'}) "
        "RETURN collect(DISTINCT d.weight), s.health"
    ).result_set == [[[100], 1.0]]
    assert scribe == [incident]
    assert api.post(f"/incidents/{incident}/resolve", json={"summary": "again"}).status_code == 400


def test_resolving_an_unknown_incident_is_a_400(api, writer):
    assert api.post("/incidents/INC-999/resolve", json={"summary": "x"}).status_code == 400
