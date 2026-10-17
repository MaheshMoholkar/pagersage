"""T2 blast_radius (G07): BFS over IMPACTS = everything that (transitively) calls a service."""

import pytest

from pagersage import seed
from pagersage.contracts import tools
from pagersage.contracts.schema import service_id
from pagersage.contracts.seed import load_seed_dir
from pagersage.contracts.tools import ToolError


def _callers_within(depth: int, target: str) -> set[str]:
    """Reference answer straight from topology.yaml: callers of `target` up to `depth` hops."""
    topology = load_seed_dir(seed.COMPANY_DIR).topology
    callers: dict[str, set[str]] = {}
    for s in topology.services:
        for d in s.depends_on:
            callers.setdefault(d.to, set()).add(s.name)
    seen, frontier = set(), {target}
    for _ in range(depth):
        frontier = {c for f in frontier for c in callers.get(f, ())} - seen - {target}
        seen |= frontier
    return {service_id(n) for n in seen}


def test_payments_db_hurts_its_callers_up_to_three_hops(tool_graph):
    impacted = tools.blast_radius("svc:payments-db")

    assert {(s.id, s.tier, s.team) for s in impacted} == {
        ("svc:api-gateway", 1, "Platform"),
        ("svc:checkout-api", 1, "Checkout"),
        ("svc:payments-svc", 1, "Payments"),
        ("svc:reconciliation-job", 2, "Ledger"),
    }
    assert impacted[-1].id == "svc:reconciliation-job"  # tier 2 after the tier-1 services


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_matches_the_topology_for_every_service(tool_graph, depth):
    topology = load_seed_dir(seed.COMPANY_DIR).topology
    for s in topology.services:
        got = {x.id for x in tools.blast_radius(service_id(s.name), depth)}
        assert got == _callers_within(depth, s.name), (s.name, depth)


def test_excludes_the_service_itself_and_orders_by_tier(tool_graph):
    impacted = tools.blast_radius("svc:kafka", 6)

    assert "svc:kafka" not in {s.id for s in impacted}
    tiers = [s.tier for s in impacted]
    assert tiers == sorted(tiers)
    assert all(s.team for s in impacted)  # every Kestrel Pay service has an owner


def test_a_service_nothing_calls_has_an_empty_blast_radius(tool_graph):
    assert tools.blast_radius("svc:edge") == []


@pytest.mark.parametrize(
    ("sid", "depth"), [("svc:nope", 3), ("payments-db", 3), ("svc:payments-db", 0)]
)
def test_bad_input_is_a_tool_error(tool_graph, sid, depth):
    with pytest.raises(ToolError):
        tools.blast_radius(sid, depth)
