"""Graph views for the canvas (task B06), shaped for @falkordb/canvas: {nodes, links}.

company()          every service (team, tier, criticality, fragility, health) and DEPENDS_ON
incident(iid)      the incident's services and their neighbours, its alerts, and every node
                   and edge its timeline events asked to highlight (root-cause path, deploy,
                   commit, people), plus the merged highlight itself
"""

from pydantic import BaseModel, Field

from pagersage import db, queries
from pagersage.contracts.events import Highlight
from pagersage.contracts.schema import Label, Rel
from pagersage.contracts.tools import ToolError, merged_highlight


class Node(BaseModel):
    id: str
    name: str
    kind: str = Field(description="Node label: Service, Alert, Deploy, Commit, Person...")
    team: str | None = None
    tier: int | None = None
    criticality: float | None = None
    fragility: float | None = None
    health: float | None = None


class Link(BaseModel):
    source: str
    target: str
    type: str = Field(description="Relationship type, e.g. DEPENDS_ON, FIRED_ON")
    weight: int | None = None
    calls_per_min: int | None = None


class GraphView(BaseModel):
    nodes: list[Node]
    links: list[Link]
    highlight: Highlight = Field(default_factory=Highlight)


def _services(graph, ids: list[str] | None) -> tuple[list[Node], list[Link]]:
    nodes = [
        Node(
            id=i,
            name=n,
            kind=Label.SERVICE,
            tier=t,
            team=team,
            criticality=c,
            fragility=f,
            health=h,
        )
        for i, n, t, team, c, f, h in graph.ro_query(
            queries.load("graph_services"), {"ids": ids}
        ).result_set
    ]
    links = [
        Link(source=a, target=b, type=Rel.DEPENDS_ON, weight=w, calls_per_min=cpm)
        for a, b, w, cpm in graph.ro_query(
            queries.load("graph_depends_on"), {"ids": ids}
        ).result_set
    ]
    return nodes, links


def company() -> GraphView:
    nodes, links = _services(db.get_graph(), None)
    return GraphView(nodes=nodes, links=links)


def incident(incident_id: str) -> GraphView:
    graph = db.get_graph()
    if not graph.ro_query(queries.load("incident_last_seq"), {"iid": incident_id}).result_set:
        raise ToolError(f"No incident with id {incident_id!r} (ids look like 'INC-051').")
    highlight = merged_highlight(graph, incident_id)
    service_ids = [
        r[0]
        for r in graph.ro_query(queries.load("incident_services"), {"iid": incident_id}).result_set
    ]
    service_ids += [n for n in highlight.nodes if n.startswith("svc:") and n not in service_ids]
    nodes, links = _services(graph, service_ids)
    for aid, sid, signal, value, _, _, _ in graph.ro_query(
        queries.load("incident_alerts"), {"iid": incident_id}
    ).result_set:
        nodes.append(Node(id=aid, name=f"{signal} {value:g}", kind=Label.ALERT))
        links.append(Link(source=aid, target=sid, type=Rel.FIRED_ON))
    shown = {n.id for n in nodes}
    extra = [n for n in highlight.nodes if n not in shown]
    if extra:
        for nid, kind, name in graph.ro_query(
            queries.load("nodes_by_id"), {"ids": extra}
        ).result_set:
            nodes.append(Node(id=nid, name=str(name), kind=kind))
        shown = {n.id for n in nodes}
    have = {(lk.source, lk.type, lk.target) for lk in links}
    links += [
        Link(source=a, target=b, type=rel)
        for a, rel, b in highlight.edges
        if (a, rel, b) not in have and a in shown and b in shown
    ]
    return GraphView(nodes=nodes, links=links, highlight=highlight)
