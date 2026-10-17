"""GET /graph (task B06): the company view, or one incident's neighbourhood with its highlight."""

from fastapi import APIRouter

from pagersage import graphview
from pagersage.graphview import GraphView

router = APIRouter(tags=["graph"])


@router.get("/graph")
def get_graph(incident: str | None = None) -> GraphView:
    """Every service and dependency, or with ?incident=INC-051 that incident's neighbourhood."""
    return graphview.incident(incident) if incident else graphview.company()
