"""Seed loader (G03): Kestrel Pay lands in the graph once, idempotently, and reset_demo brings
back exactly the seed state."""

from datetime import UTC, datetime

import pytest

from pagersage import seed
from pagersage.contracts.seed import load_history_dir, load_seed_dir


@pytest.fixture(scope="module")
def files():
    company = load_seed_dir(seed.COMPANY_DIR)
    return company, load_history_dir(seed.HISTORY_DIR, company)


@pytest.fixture
def seeded(graph):
    return graph, seed.seed_graph(graph)


def _one(graph, query, params=None):
    [[value]] = graph.ro_query(query, params).result_set
    return value


def test_every_record_becomes_a_node(seeded, files):
    _, counts = seeded
    company, history = files
    incidents = history.incidents

    assert counts["Service"] == len(company.topology.services)
    assert counts["Team"] == len(company.org.teams)
    assert counts["Person"] == len(company.org.people)
    assert counts["Runbook"] == len(company.runbooks.runbooks)
    assert counts["Policy"] == len(company.policies.policies)
    assert counts["Deploy"] == len(history.deploys)
    assert counts["Commit"] == len(history.commits)
    assert counts["ConfigChange"] == len(history.config_changes)
    assert counts["Incident"] == len(incidents)
    assert counts["Alert"] == sum(len(i.alerts) for i in incidents)
    assert counts["Event"] == sum(len(i.timeline) for i in incidents)
    assert counts["Postmortem"] == sum(1 for i in incidents if i.postmortem)


def test_every_reference_becomes_an_edge(seeded, files):
    _, counts = seeded
    company, history = files
    incidents = history.incidents

    assert counts["DEPENDS_ON"] == sum(len(s.depends_on) for s in company.topology.services)
    assert counts["OWNS"] == len(company.topology.services)  # exactly one owner each
    assert counts["MEMBER_OF"] == len(company.org.people)
    assert counts["ON_CALL"] == sum(len(r) for r in company.org.on_call.teams.values())
    assert counts["FOR"] == len(company.runbooks.runbooks)
    assert counts["AUTHORED"] == counts["CONTAINS"] == len(history.commits)
    assert counts["TARGETED"] == counts["DEPLOYED"] == len(history.deploys)
    assert counts["CHANGED"] == counts["MADE"] == len(history.config_changes)
    assert counts["AFFECTED"] == sum(len(i.affected) for i in incidents)
    assert counts["CAUSED_BY"] == sum(len(i.caused_by) for i in incidents)
    assert counts["FIRED_ON"] == sum(len(i.alerts) for i in incidents)
    assert counts["NEXT"] == sum(len(i.timeline) - 1 for i in incidents)
    # RESOLVED: one per runbook outcome plus one per person who resolved an incident
    assert counts["RESOLVED"] == sum(len(i.runbooks) for i in incidents) + len(incidents)
    assert counts["ABOUT"] == counts["WROTE"] == counts["Postmortem"]


def test_impacts_is_the_exact_reverse_of_depends_on(seeded):
    graph, counts = seeded

    assert counts["IMPACTS"] == counts["DEPENDS_ON"]
    unmatched = "MATCH (a)-[:DEPENDS_ON]->(b) WHERE NOT (b)-[:IMPACTS]->(a) RETURN count(*)"
    assert _one(graph, unmatched) == 0


def test_seeding_twice_changes_nothing(seeded):
    graph, first = seeded

    assert seed.seed_graph(graph) == first


def test_reset_restores_the_seed_state(seeded):
    graph, first = seeded
    # what a scenario run leaves behind: a live deploy, a sick service, a hot edge
    graph.query(
        "MATCH (s:Service {id:'svc:payments-db'}) SET s.health = 0.2 "
        "CREATE (:Deploy {id:'dep-0416', ts:1, version:'v9', status:'ok', env:'prod'})"
        "-[:TARGETED]->(s)"
    )
    graph.query("MATCH ()-[d:DEPENDS_ON]->(:Service {id:'svc:payments-db'}) SET d.weight = 80")

    assert seed.reset_demo(graph) == first
    assert _one(graph, "MATCH (d:Deploy {id:'dep-0416'}) RETURN count(d)") == 0
    assert _one(graph, "MATCH (s:Service {id:'svc:payments-db'}) RETURN s.health") == 1.0
    assert _one(graph, "MATCH ()-[d:DEPENDS_ON]->() RETURN collect(DISTINCT d.weight)") == [100]


def test_reset_works_on_an_empty_graph(graph):
    assert seed.reset_demo(graph)["Service"] > 0


def test_pool_exhaustion_history_is_walkable(seeded):
    # The demo's precedent: payments-db pool cuts caused INC-019/031/042, and the
    # "raise pool" runbook fixed all three.
    graph, _ = seeded
    caused = graph.ro_query(
        "MATCH (i:Incident)-[:CAUSED_BY]->(c:ConfigChange)-[:CHANGED]->"
        "(:Service {id:'svc:payments-db'}) RETURN i.id ORDER BY i.id"
    ).result_set
    assert {r[0] for r in caused} >= {"INC-019", "INC-031", "INC-042"}
    runbook = graph.ro_query(
        "MATCH (rb:Runbook {id:'rb:raise-payments-db-pool'})-[:FOR]->(s:Service) "
        "RETURN s.id, rb.success_count, rb.fail_count"
    ).result_set
    assert runbook == [["svc:payments-db", 3, 0]]


def test_commit_id_is_the_sha(seeded):
    graph, _ = seeded
    assert _one(graph, "MATCH (c:Commit) WHERE c.id <> c.sha RETURN count(c)") == 0


def test_timeline_is_a_chain_from_seq_1(seeded):
    graph, _ = seeded
    rows = graph.ro_query(
        "MATCH (e:Event)-[:PART_OF]->(:Incident {id:'INC-042'}) "
        "RETURN e.seq, e.kind, e.agent ORDER BY e.seq"
    ).result_set
    assert rows[0][0] == 1
    assert all(agent is None for _, _, agent in rows)  # people handled past incidents
    path_len = _one(
        graph,
        "MATCH p = (first:Event {id:'evt:INC-042:1'})-[:NEXT*]->(last:Event) "
        "WHERE NOT (last)-[:NEXT]->() RETURN length(p)",
    )
    assert path_len == len(rows) - 1


def test_priya_is_on_call_for_payments_during_the_demo_week(seeded):
    graph, _ = seeded
    now = int(datetime(2026, 10, 16, 12, tzinfo=UTC).timestamp())
    rows = graph.ro_query(
        "MATCH (p:Person)-[oc:ON_CALL]->(:Team {id:'team:payments'}) "
        "WHERE oc.from <= $now AND oc.to > $now RETURN p.id",
        {"now": now},
    ).result_set
    assert rows == [["person:priya"]]
