"""Kestrel Pay's real company files, checked the way PagerSage will ingest them. A bad Kestrel
Pay file should fail here, not in the demo. The planted patterns the demo relies on are
asserted by Kestrel Pay's own tests (kestrel-pay/tests/); this file checks what only
PagerSage's side can: the formats and what FalkorDB itself computes from them."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from pagersage.contracts.schema import Label, Rel
from pagersage.contracts.seed import SeedBundle, Topology, load_history_dir, load_seed_dir

KESTREL = Path(__file__).resolve().parents[2] / "kestrel-pay"
COMPANY = KESTREL / "company"


@pytest.fixture(scope="module")
def topology() -> Topology:
    return Topology.model_validate(yaml.safe_load((COMPANY / "topology.yaml").read_text()))


@pytest.fixture(scope="module")
def bundle() -> SeedBundle:
    return load_seed_dir(COMPANY)


def test_topology_is_valid(topology):
    assert 20 <= len(topology.services) <= 30
    assert all(s.description.strip() for s in topology.services)


def test_org_is_valid(bundle):
    # load_seed_dir already checks one owner per service and on-call membership.
    assert len(bundle.org.teams) == 6
    assert 25 <= len(bundle.org.people) <= 35


def test_on_call_covers_oct_12_to_25(bundle):
    # Rotations repeat forever; what matters is a rotation per team from Oct 12, and a
    # different person each week so the demo pages someone specific.
    oc = bundle.org.on_call
    assert set(oc.teams) == {t.slug for t in bundle.org.teams}, "every team needs a rotation"
    assert oc.start <= date(2026, 10, 12)
    for team, rota in oc.teams.items():
        on_call = {
            rota[((day - oc.start).days // oc.rotation_days) % len(rota)]
            for day in (date(2026, 10, 12), date(2026, 10, 19))
        }
        assert len(on_call) == 2, f"{team}: weeks of Oct 12 and Oct 19 need different people"


def _betweenness(graph, topology: Topology, sampling_size: int | None) -> list[str]:
    for s in topology.services:
        graph.query(f"CREATE (:{Label.SERVICE} {{id: $id}})", {"id": s.name})
    for s in topology.services:
        for d in s.depends_on:
            graph.query(
                f"MATCH (a:{Label.SERVICE} {{id: $a}}), (b:{Label.SERVICE} {{id: $b}}) "
                f"CREATE (a)-[:{Rel.DEPENDS_ON}]->(b)",
                {"a": s.name, "b": d.to},
            )
    sampling = ", samplingSize: $n" if sampling_size else ""
    rows = graph.query(
        f"CALL algo.betweenness({{nodeLabels: ['{Label.SERVICE}'], "
        f"relationshipTypes: ['{Rel.DEPENDS_ON}'], samplingSeed: 42{sampling}}}) "
        "YIELD node, score RETURN node.id ORDER BY score DESC",
        {"n": sampling_size},
    ).result_set
    return [r[0] for r in rows]


@pytest.mark.parametrize("exact", [False, True], ids=["plan-call", "exact"])
def test_kafka_is_most_fragile(graph, topology, exact):
    # Planted pattern 3. The plan's batch call (no samplingSize) samples a few source nodes;
    # samplingSize >= node count gives exact scores. kafka must win either way.
    ranked = _betweenness(graph, topology, len(topology.services) if exact else None)
    assert ranked[0] == "kafka"


def test_runbooks_and_policies_the_demo_needs(bundle):
    by_slug = {rb.slug: rb for rb in bundle.runbooks.runbooks}
    assert by_slug["raise-payments-db-pool"].service == "payments-db"
    rollback = {p.slug: p for p in bundle.policies.policies}["tier1-rollback-ack"]
    assert rollback.actions == ["rollback"]
    assert rollback.max_tier == 1


def test_history_export_is_valid(bundle):
    history = load_history_dir(KESTREL / "history" / "export", bundle)
    assert len(history.incidents) == 40
    assert len(history.config_changes) == 60
