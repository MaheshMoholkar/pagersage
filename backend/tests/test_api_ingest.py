"""POST /ingest/deploy and /ingest/config-change (B10), with the injector's own payloads."""

import pytest

from pagersage.contracts import tools

NOW = 1_792_500_000
SHA = "1a132292cfe942b80c1846e1bcf9769685f18a79"
DEPLOY = {
    "id": "dep-0416",
    "service": "payments-svc",
    "version": "v3.25.2",
    "ts": NOW - 360,
    "deployed_by": "tomas",
    "commits": [
        {
            "sha": SHA,
            "message": "payments-db: lower max_pool_size to 60 to cut idle connections",
            "author": "tomas",
            "ts": NOW - 900,
        }
    ],
}
CONFIG = {
    "id": "cfg-0061",
    "service": "payments-db",
    "key": "max_pool_size",
    "old": "200",
    "new": "60",
    "ts": NOW - 360,
    "made_by": "tomas",
}


def _one(g, q):
    [[v]] = g.ro_query(q).result_set
    return v


def test_deploy_lands_with_its_commit_service_and_people(api, writer):
    r = api.post("/ingest/deploy", json=DEPLOY)

    assert (r.status_code, r.json()) == (200, {"id": "dep-0416", "service_id": "svc:payments-svc"})
    assert writer.ro_query(
        "MATCH (p:Person)-[:DEPLOYED]->(d:Deploy {id:'dep-0416'})-[:TARGETED]->(s:Service), "
        "(d)-[:CONTAINS]->(c:Commit)<-[:AUTHORED]-(a:Person) "
        "RETURN p.id, s.id, c.id, c.sha, a.id, d.status, d.env, d.version"
    ).result_set == [
        ["person:tomas", "svc:payments-svc", SHA, SHA, "person:tomas", "ok", "prod", "v3.25.2"]
    ]


def test_config_change_lands_on_its_service(api, writer):
    r = api.post("/ingest/config-change", json=CONFIG)

    assert r.status_code == 200
    assert writer.ro_query(
        "MATCH (p:Person)-[:MADE]->(c:ConfigChange {id:'cfg-0061'})-[:CHANGED]->(s:Service) "
        "RETURN p.id, s.id, c.key, c.old, c.new"
    ).result_set == [["person:tomas", "svc:payments-db", "max_pool_size", "200", "60"]]


def test_posting_again_changes_nothing(api, writer):
    count = "MATCH (n) WHERE n.id IN ['dep-0416', 'cfg-0061', $sha] RETURN count(n)"
    edges = "MATCH (n)-[e]-() WHERE n.id IN ['dep-0416', 'cfg-0061'] RETURN count(e)"
    api.post("/ingest/deploy", json=DEPLOY)
    api.post("/ingest/config-change", json=CONFIG)
    before = (
        writer.ro_query(count, {"sha": SHA}).result_set,
        _one(writer, edges),
    )

    assert api.post("/ingest/deploy", json=DEPLOY).status_code == 200
    assert api.post("/ingest/config-change", json=CONFIG).status_code == 200
    assert (writer.ro_query(count, {"sha": SHA}).result_set, _one(writer, edges)) == before


def test_ingested_changes_become_suspects(api, writer, monkeypatch):
    api.post("/ingest/deploy", json=DEPLOY)
    api.post("/ingest/config-change", json=CONFIG)
    monkeypatch.setattr(tools, "_now", lambda: NOW)

    found = {s.change_id for s in tools.suspect_changes("svc:checkout-api", NOW - 3600)}

    assert {"dep-0416", "cfg-0061"} <= found


@pytest.mark.parametrize(
    ("path", "patch", "status"),
    [
        ("/ingest/deploy", {"service": "nope-svc"}, 400),  # unknown service
        ("/ingest/deploy", {"deployed_by": "nobody"}, 400),  # unknown person
        ("/ingest/deploy", {"id": "deploy-1"}, 422),  # not a deploy id
        ("/ingest/deploy", {"commits": []}, 422),
        ("/ingest/config-change", {"made_by": "nobody"}, 400),
        ("/ingest/config-change", {"extra": 1}, 422),
    ],
)
def test_bad_input_is_rejected(api, writer, path, patch, status):
    body = (DEPLOY if path.endswith("deploy") else CONFIG) | patch

    r = api.post(path, json=body)

    assert r.status_code == status, r.text
    if status == 400:
        assert "Unknown" in r.json()["error"]
