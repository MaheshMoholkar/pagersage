"""Live-weight updater (G09): a sick service's incoming DEPENDS_ON edges get cheap, so the
weighted shortest path runs through the sick part of the system."""

import pytest

from pagersage import db
from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError, live_weight


@pytest.mark.parametrize(
    ("health", "weight"), [(1.0, 100), (0.999, 100), (0.4, 40), (0.15, 15), (0.03, 5), (0.0, 5)]
)
def test_weight_is_health_as_an_integer_percentage_clipped_to_5_100(health, weight):
    assert live_weight(health) == weight


# a calls b and c; both call d. Two equally long routes from a to d.
TOY = """
CREATE (a:Service {id:'svc:a', health:1.0}), (b:Service {id:'svc:b', health:1.0}),
       (c:Service {id:'svc:c', health:1.0}), (d:Service {id:'svc:d', health:1.0}),
       (a)-[:DEPENDS_ON {weight:100}]->(b), (a)-[:DEPENDS_ON {weight:100}]->(c),
       (b)-[:DEPENDS_ON {weight:100}]->(d), (c)-[:DEPENDS_ON {weight:100}]->(d)
"""
SHORTEST = """
MATCH (a:Service {id:'svc:a'}), (d:Service {id:'svc:d'})
CALL algo.SPpaths({sourceNode:a, targetNode:d, relTypes:['DEPENDS_ON'],
                   relDirection:'outgoing', weightProp:'weight', pathCount:1})
YIELD path, pathWeight
RETURN [n IN nodes(path) | n.id], pathWeight
"""


@pytest.fixture
def toy(graph, monkeypatch):
    graph.query(TOY)
    monkeypatch.setattr(db, "get_graph", lambda name=None: graph)
    return graph


def test_shortest_path_moves_through_the_sick_service(toy):
    tools.update_live_weights("svc:b", 0.2)
    assert toy.ro_query(SHORTEST).result_set == [[["svc:a", "svc:b", "svc:d"], 120]]

    tools.update_live_weights("svc:b", 1.0)
    tools.update_live_weights("svc:c", 0.1)
    assert toy.ro_query(SHORTEST).result_set == [[["svc:a", "svc:c", "svc:d"], 110]]


def test_only_edges_into_the_service_change(toy):
    tools.update_live_weights("svc:b", 0.15)

    rows = toy.ro_query(
        "MATCH (x)-[e:DEPENDS_ON]->(y) RETURN x.id, y.id, e.weight ORDER BY x.id, y.id"
    ).result_set
    assert rows == [
        ["svc:a", "svc:b", 15],
        ["svc:a", "svc:c", 100],
        ["svc:b", "svc:d", 100],
        ["svc:c", "svc:d", 100],
    ]
    assert all(isinstance(w, int) for *_, w in rows)  # integers, as pathWeight expects
    [[health]] = toy.ro_query("MATCH (s:Service {id:'svc:b'}) RETURN s.health").result_set
    assert health == 0.15


def test_a_service_nothing_calls_still_records_its_health(toy):
    tools.update_live_weights("svc:a", 0.5)

    [[health]] = toy.ro_query("MATCH (s:Service {id:'svc:a'}) RETURN s.health").result_set
    assert health == 0.5


@pytest.mark.parametrize(("sid", "health"), [("svc:nope", 0.5), ("svc:b", 1.5), ("svc:b", -0.1)])
def test_bad_input_is_a_tool_error(toy, sid, health):
    with pytest.raises(ToolError):
        tools.update_live_weights(sid, health)
