"""Batch graph algorithms (task G05; build-plan.md section 4, "Batch jobs").

Run after every seed (`seed_graph` calls `run_batch`):
- Service.fragility   = algo.betweenness on DEPENDS_ON (fragile_services, suspect ranking)
- Service.criticality = algo.pageRank on DEPENDS_ON (blast radius order, canvas node size)
- ownership gaps      = algo.wcc over OWNS: services in a component with no Team
- Person.community    = algo.labelPropagation over COLLABORATES (G18): real teams
"""

from falkordb import Graph

from pagersage import queries
from pagersage.contracts.schema import Label


def compute_scores(graph: Graph) -> None:
    """Write fragility and criticality onto every Service."""
    nodes = dict(graph.ro_query(queries.load("count_nodes")).result_set)
    # samplingSize must cover every service, or betweenness samples and the ranking can shift.
    sampling = max(nodes.get(Label.SERVICE, 0), 1)
    graph.query(queries.load("batch_fragility"), {"sampling": sampling})
    graph.query(queries.load("batch_criticality"))


def ownership_gaps(graph: Graph) -> list[str]:
    """Ids of services no team owns, sorted."""
    return [row[0] for row in graph.ro_query(queries.load("ownership_gaps")).result_set]


# Two people collaborate when their commits shipped together in at least this many deploys.
# At 1-2, a handful of cross-team deploys joins nearly everyone into one community.
MIN_SHARED_DEPLOYS = 3


def compute_real_teams(graph: Graph) -> None:
    """Write COLLABORATES edges and Person.community."""
    graph.query(queries.load("batch_collaborates"), {"min_deploys": MIN_SHARED_DEPLOYS})
    graph.query(queries.load("batch_communities"))


def real_teams(graph: Graph) -> list[dict]:
    """Communities from shipping together, largest first, each with its members' org-chart
    teams: [{"community": 1, "members": [{"handle", "name", "team"}], "teams": [names]}]."""
    return [
        {
            "community": community,
            "members": sorted(members, key=lambda m: (m["team"], m["handle"])),
            "teams": sorted({m["team"] for m in members}),
        }
        for community, members in graph.ro_query(queries.load("real_teams")).result_set
    ]


def run_batch(graph: Graph) -> list[str]:
    """Compute every batch score. Returns the ownership gaps (empty when every service is owned)."""
    compute_scores(graph)
    compute_real_teams(graph)
    return ownership_gaps(graph)
