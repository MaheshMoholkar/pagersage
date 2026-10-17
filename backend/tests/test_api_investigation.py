"""GET /incidents/{id}/suspects and /memory (U06, U07): the Investigator's and Historian's reads
rerun for the Investigation screen, on the pool-exhaustion scenario."""

import itertools

import pytest

from pagersage.contracts import tools
from tests import scenario

_ids = itertools.count(40)


@pytest.fixture
def incident(writer, monkeypatch):
    """The scenario's changes and health, plus a fresh incident with both of its alerts."""
    if not writer.ro_query("MATCH (c:ConfigChange {id:'cfg-0061'}) RETURN c.id").result_set:
        writer.query(scenario.SCENARIO, {"now": scenario.NOW})
        for sid, health in scenario.HEALTH.items():
            tools.update_live_weights(sid, health)
    monkeypatch.setattr(tools, "_now", lambda: scenario.NOW)
    iid = f"INC-2{next(_ids):02d}"
    writer.query(
        "MATCH (db:Service {id:'svc:payments-db'}), (co:Service {id:'svc:checkout-api'}) "
        "CREATE (i:Incident {id:$id, title:'payments-db saturation', severity:'sev1', "
        "status:'open', opened_at:$now, summary:''}), "
        "(a:Alert {id:$a1, ts:$now, signal:'saturation', value:0.99, threshold:0.9, "
        "severity:'sev2'})-[:PART_OF]->(i), (a)-[:FIRED_ON]->(db), "
        "(b:Alert {id:$a2, ts:$now + 20, signal:'error_rate', value:8.4, threshold:1.0, "
        "severity:'sev1'})-[:PART_OF]->(i), (b)-[:FIRED_ON]->(co)",
        {"id": iid, "now": scenario.NOW, "a1": f"alt-8{iid[-3:]}1", "a2": f"alt-8{iid[-3:]}2"},
    )
    return iid


def _triage(iid):
    inc = scenario.LIVE_INCIDENT
    tools.set_triage(iid, inc["title"], "sev1", scenario.PATH, inc["summary"])


def test_suspects_rank_from_the_service_users_hit(api, incident):
    r = api.get(f"/incidents/{incident}/suspects")

    assert r.status_code == 200
    body = r.json()
    assert body["alerting_service_id"] == "svc:checkout-api"  # fewer callers than payments-db
    assert body["since"] == scenario.NOW - 7200
    assert [s["change_id"] for s in body["suspects"]] == ["cfg-0061", "dep-0417", "dep-0416"]
    assert set(body["suspects"][0]["score_parts"]) == {
        "recency",
        "distance",
        "fragility",
        "anomaly",
    }
    assert (body["cause"], body["rejected"]) == (None, [])


def test_suspects_show_the_cause_and_what_was_ruled_out(api, writer, incident):
    tools.record_cause(incident, "cfg-0061", 0.9)
    writer.query(
        "MATCH (i:Incident {id:$i}) SET i.state = $s",
        {"i": incident, "s": '{"path": ["svc:checkout-api"], "rejected": ["dep-0417"]}'},
    )

    body = api.get(f"/incidents/{incident}/suspects").json()

    assert (body["cause"], body["rejected"]) == ("cfg-0061", ["dep-0417"])


def test_memory_waits_for_triage_then_ranks_with_the_graph(api, incident):
    before = api.get(f"/incidents/{incident}/memory").json()
    _triage(incident)

    after = api.get(f"/incidents/{incident}/memory").json()

    assert before["similar"] is None
    assert after["path"] == sorted(scenario.PATH)  # AFFECTED, until the agents store the path
    assert [i["id"] for i in after["similar"]["graph_ranked"]] == ["INC-042", "INC-031", "INC-019"]
    assert after["runbook_service_id"] == "svc:payments-db"  # the deepest alerting service
    assert after["runbooks"][0]["id"] == "rb:raise-payments-db-pool"


def test_memory_uses_the_agents_path_and_cause_service(api, writer, incident):
    _triage(incident)
    writer.query(
        "MATCH (i:Incident {id:$i}) SET i.state = $s",
        {
            "i": incident,
            "s": '{"path": ["svc:checkout-api", "svc:payments-svc", "svc:payments-db"], '
            '"cause_service": "svc:payments-db"}',
        },
    )

    body = api.get(f"/incidents/{incident}/memory").json()

    assert body["path"] == scenario.PATH
    assert body["runbook_service_id"] == "svc:payments-db"
    assert body["runbooks"][0]["id"] == "rb:raise-payments-db-pool"


@pytest.mark.parametrize("view", ["suspects", "memory"])
def test_unknown_incident_is_a_400(api, writer, view):
    r = api.get(f"/incidents/INC-999/{view}")

    assert r.status_code == 400 and "No incident" in r.json()["error"]
