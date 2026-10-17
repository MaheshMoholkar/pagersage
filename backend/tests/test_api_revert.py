"""POST /incidents/{id}/revert (U09): a person reverts the cause, config change or deploy
(simulated in the graph); the incident becomes mitigated. Plus the postmortem in the detail."""

import itertools
import json

import pytest

from pagersage.contracts import tools
from tests import scenario

_ids = itertools.count(60)


@pytest.fixture
def incident(writer, monkeypatch):
    if not writer.ro_query("MATCH (c:ConfigChange {id:'cfg-0061'}) RETURN c.id").result_set:
        writer.query(scenario.SCENARIO, {"now": scenario.NOW})
    monkeypatch.setattr(tools, "_now", lambda: scenario.NOW + 600)
    iid = f"INC-3{next(_ids):02d}"
    writer.query(
        "CREATE (:Incident {id:$id, title:'checkout errors', severity:'sev1', "
        "status:'investigating', opened_at:$now, summary:''})",
        {"id": iid, "now": scenario.NOW},
    )
    return iid


def _status(g, iid):
    return g.ro_query("MATCH (i:Incident {id:$i}) RETURN i.status", {"i": iid}).result_set[0][0]


def test_reverting_a_config_change_sets_the_key_back(api, writer, incident):
    r = api.post(f"/incidents/{incident}/revert", json={"change_id": "cfg-0061"})

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["action"] == "rollback"
    assert body["detail"].startswith("Simulated revert: payments-db max_pool_size back to 100")
    [[new, key, old, value, status, simulated]] = writer.ro_query(
        "MATCH (n:ConfigChange)-[:ROLLED_BACK]->(o:ConfigChange {id:'cfg-0061'}), "
        "(n)-[:CHANGED]->(:Service {id:'svc:payments-db'}) "
        "RETURN n.id, n.key, n.old, n.new, o.status, n.simulated"
    ).result_set
    assert (key, old, value, status, simulated) == (
        "max_pool_size",
        "60",
        "100",
        "rolled_back",
        True,
    )
    assert new in body["detail"]
    assert _status(writer, incident) == "mitigated"
    [[kind, data]] = writer.ro_query(
        "MATCH (e:Event {incident_id:$i}) RETURN e.kind, e.data", {"i": incident}
    ).result_set
    assert kind == "action" and json.loads(data)["change_id"] == "cfg-0061"


def test_a_change_is_reverted_once(api, writer, incident):
    api.post(f"/incidents/{incident}/revert", json={"change_id": "cfg-0061"})  # may be done
    r = api.post(f"/incidents/{incident}/revert", json={"change_id": "cfg-0061"})

    assert r.status_code == 400 and "already reverted" in r.json()["error"]


def test_reverting_a_deploy_rolls_it_back(api, writer, incident):
    r = api.post(f"/incidents/{incident}/revert", json={"change_id": "dep-0417"})

    assert r.status_code == 200 and r.json()["detail"].startswith(
        "Simulated rollback: checkout-api"
    )
    assert _status(writer, incident) == "mitigated"


@pytest.mark.parametrize(
    ("iid", "change", "hint"),
    [("INC-999", "cfg-0061", "No incident"), (None, "cfg-9999", "No change")],
)
def test_bad_reverts_are_400s(api, writer, incident, iid, change, hint):
    r = api.post(f"/incidents/{iid or incident}/revert", json={"change_id": change})

    assert r.status_code == 400 and hint in r.json()["error"]


def test_resolved_incidents_are_not_reverted(api, writer, incident):
    writer.query("MATCH (i:Incident {id:$i}) SET i.status = 'resolved'", {"i": incident})

    r = api.post(f"/incidents/{incident}/revert", json={"change_id": "cfg-0061"})

    assert r.status_code == 400 and "already resolved" in r.json()["error"]


def test_the_detail_carries_the_scribes_postmortem(api, writer, incident):
    assert api.get(f"/incidents/{incident}").json()["postmortem"] is None
    writer.query("MATCH (i:Incident {id:$i}) SET i.status = 'resolved'", {"i": incident})
    tools.write_postmortem(incident, "Pool cut", "## What happened\nCheckout failed.")

    pm = api.get(f"/incidents/{incident}").json()["postmortem"]

    body = "## What happened\nCheckout failed."
    assert pm == {"title": "Pool cut", "body": body, "ts": scenario.NOW + 600}
