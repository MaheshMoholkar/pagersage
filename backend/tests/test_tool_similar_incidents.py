"""T6 similar_incidents (G12): vector search finds candidates, the graph ranks them."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError
from tests.scenario import LIVE_INCIDENT, PATH


def _ids(items):
    return [x.id for x in items]


def test_graph_ranking_puts_the_latest_pool_precedent_first(scenario):
    result = tools.similar_incidents(LIVE_INCIDENT["id"], PATH)

    # Vector-only: closest text first. Graph: all three share the whole path and a cause on
    # payments-db, so the newest precedent (INC-042) wins. Kestrel Pay's expected answer.
    assert _ids(result.vector_only) == ["INC-019", "INC-031", "INC-042"]
    assert _ids(result.graph_ranked) == ["INC-042", "INC-031", "INC-019"]


def test_precedents_carry_shared_services_runbooks_and_postmortems(scenario):
    top = tools.similar_incidents(LIVE_INCIDENT["id"], PATH).graph_ranked[0]

    assert top.shared_services == 3
    assert 0 < top.score <= 1  # cosine similarity, 1 - the index's distance
    assert [(r.id, r.success_count) for r in top.runbooks] == [("rb:raise-payments-db-pool", 3)]
    assert top.postmortem_titles and all(top.postmortem_titles)


def test_only_runbooks_that_worked_are_listed(scenario):
    by_id = {
        i.id: i for i in tools.similar_incidents(LIVE_INCIDENT["id"], PATH, limit=5).graph_ranked
    }
    # INC-019: failover-payments-db failed, raise-payments-db-pool worked
    assert _ids(by_id["INC-019"].runbooks) == ["rb:raise-payments-db-pool"]


def test_both_lists_hold_the_same_candidates(scenario):
    result = tools.similar_incidents(LIVE_INCIDENT["id"], PATH, limit=5)

    assert len(result.graph_ranked) == len(result.vector_only) == 5
    assert LIVE_INCIDENT["id"] not in _ids(result.vector_only)
    scores = [i.score for i in result.vector_only]
    assert scores == sorted(scores, reverse=True)


def test_without_a_path_the_text_decides(scenario):
    result = tools.similar_incidents(LIVE_INCIDENT["id"], [])

    assert _ids(result.graph_ranked)[0] == "INC-019"  # no graph evidence: fall back to sim


@pytest.mark.parametrize(("iid", "limit"), [("INC-999", 3), ("INC-051", 0), ("INC-051", 11)])
def test_bad_input_is_a_tool_error(scenario, iid, limit):
    with pytest.raises(ToolError):
        tools.similar_incidents(iid, PATH, limit)


def test_an_incident_without_an_embedding_is_a_tool_error(graph, monkeypatch):
    from pagersage import db

    graph.query("CREATE (:Incident {id:'INC-052', title:'t'})")
    monkeypatch.setattr(db, "get_graph", lambda name=None: graph)
    with pytest.raises(ToolError, match="set_triage"):
        tools.similar_incidents("INC-052", PATH)
