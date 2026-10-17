"""Indexes and constraints (G02): what ensure_indexes creates, that it is idempotent, and that
the unique `id` constraint and the vector/full-text indexes actually work."""

import pytest
from redis.exceptions import ResponseError

from pagersage import indexes
from pagersage.contracts.schema import Label


def _index_types(graph) -> set[tuple[str, str, str]]:
    rows = graph.query("CALL db.indexes() YIELD label, types RETURN label, types").result_set
    return {(label, prop, t) for label, types in rows for prop, ts in types.items() for t in ts}


def test_every_label_gets_a_unique_id():
    assert {label for label, prop in indexes.UNIQUE if prop == "id"} == set(Label)
    assert set(indexes.UNIQUE) <= set(indexes.RANGE)  # a unique constraint needs a range index


def test_creates_every_index_and_constraint(graph):
    indexes.ensure_indexes(graph)

    have = _index_types(graph)
    for label, prop in indexes.RANGE:
        assert (label, prop, "RANGE") in have
    assert (Label.COMMIT, "sha", "RANGE") in have
    assert (Label.SERVICE, "name", "FULLTEXT") in have
    assert (Label.SERVICE, "description", "FULLTEXT") in have
    assert (Label.INCIDENT, "embedding", "VECTOR") in have

    constraints = {
        (c["label"], tuple(c["properties"]), c["status"]) for c in graph.list_constraints()
    }
    for label, prop in indexes.UNIQUE:
        assert (label, (prop,), "OPERATIONAL") in constraints


def test_second_run_creates_nothing(graph):
    first = indexes.ensure_indexes(graph)
    before = (_index_types(graph), len(graph.list_constraints()))

    assert first  # an empty graph needed everything
    assert indexes.ensure_indexes(graph) == []
    assert (_index_types(graph), len(graph.list_constraints())) == before


def test_fills_in_a_partial_setup(graph):
    # e.g. someone created the full-text index by hand with only one field
    graph.query("CREATE FULLTEXT INDEX FOR (s:Service) ON (s.name)")

    created = indexes.ensure_indexes(graph)

    assert "fulltext Service.description" in created
    assert "fulltext Service.name" not in created
    assert (Label.SERVICE, "description", "FULLTEXT") in _index_types(graph)


def test_duplicate_id_is_rejected(graph):
    indexes.ensure_indexes(graph)
    graph.query("CREATE (:Service {id:'svc:payments-db'})")

    with pytest.raises(ResponseError, match="unique constraint violation"):
        graph.query("CREATE (:Service {id:'svc:payments-db'})")


def test_vector_index_is_384_dim_cosine(graph):
    indexes.ensure_indexes(graph)
    v = [1.0] + [0.0] * (indexes.EMBEDDING_DIM - 1)
    graph.query("CREATE (:Incident {id:'INC-001', embedding:vecf32($v)})", {"v": v})

    rows = graph.ro_query(
        "CALL db.idx.vector.queryNodes('Incident', 'embedding', 1, vecf32($v)) "
        "YIELD node, score RETURN node.id, score",
        {"v": v},
    ).result_set

    assert rows[0][0] == "INC-001"
    assert rows[0][1] == pytest.approx(0.0, abs=1e-5)  # cosine distance to itself


def test_fulltext_finds_services_by_name_and_description(graph):
    indexes.ensure_indexes(graph)
    graph.query(
        "CREATE (:Service {id:'svc:payments-api', name:'payments-api', description:'card auth'}), "
        "(:Service {id:'svc:ledger-svc', name:'ledger-svc', description:'double-entry payments'})"
    )
    query = "CALL db.idx.fulltext.queryNodes('Service', $q) YIELD node RETURN node.id"

    found = {r[0] for r in graph.ro_query(query, {"q": "%paymnts%"}).result_set}

    assert found == {"svc:payments-api", "svc:ledger-svc"}


def test_wrong_vector_dimension_is_an_error(graph):
    graph.query(
        "CREATE VECTOR INDEX FOR (i:Incident) ON (i.embedding) "
        "OPTIONS {dimension:3, similarityFunction:'cosine'}"
    )

    with pytest.raises(indexes.IndexSetupError, match="dimension"):
        indexes.ensure_indexes(graph)
