"""Incident embeddings (G04): all-MiniLM-L6-v2 via fastembed, stored as vecf32 on Incident."""

import math

import pytest

from pagersage import embeddings, seed
from pagersage.indexes import EMBEDDING_DIM


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))  # vectors are unit length


def test_vectors_match_the_index():
    [v] = embeddings.embed(["payments-db connection pool exhausted"])

    assert len(v) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in v)
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-4)


def test_similar_incidents_are_closer_than_unrelated_ones():
    pool, pool_again, orjson = embeddings.embed(
        [
            embeddings.incident_text(
                "payments-db pool exhausted", "checkout errors after the pool was cut"
            ),
            embeddings.incident_text(
                "payments-svc timeouts", "payments-db connection pool exhausted"
            ),
            embeddings.incident_text(
                "checkout-api 5xx", "orjson cannot encode Decimal prices in carts"
            ),
        ]
    )

    assert _cos(pool, pool_again) > _cos(pool, orjson)


def test_incident_text_uses_title_and_summary():
    assert embeddings.incident_text("Title", "Summary.") == "Title\nSummary."


@pytest.fixture
def seeded(graph):
    seed.seed_graph(graph)
    return graph


def test_seed_embeds_every_past_incident(seeded):
    missing = seeded.ro_query(
        "MATCH (i:Incident) WHERE i.embedding IS NULL RETURN count(i)"
    ).result_set
    assert missing == [[0]]


def test_an_incident_finds_itself(seeded):
    title, summary = seeded.ro_query(
        "MATCH (i:Incident {id:'INC-042'}) RETURN i.title, i.summary"
    ).result_set[0]
    [v] = embeddings.embed([embeddings.incident_text(title, summary)])

    [[top, distance]] = seeded.ro_query(
        "CALL db.idx.vector.queryNodes('Incident', 'embedding', 1, vecf32($v)) "
        "YIELD node, score RETURN node.id, score",
        {"v": v},
    ).result_set

    assert top == "INC-042"
    assert distance == pytest.approx(0.0, abs=1e-4)


def test_a_new_pool_incident_finds_the_pool_precedents(seeded):
    # What triage will embed for the live pool-exhaustion scenario (A04, T6).
    [v] = embeddings.embed(
        [
            embeddings.incident_text(
                "checkout-api errors: payments-db connection pool exhausted",
                "payments-svc cannot get connections from payments-db; checkout fails.",
            )
        ]
    )

    rows = seeded.ro_query(
        "CALL db.idx.vector.queryNodes('Incident', 'embedding', 3, vecf32($v)) "
        "YIELD node RETURN node.id",
        {"v": v},
    ).result_set

    # Vector-only finds all three pool incidents; G12's graph re-ranking puts INC-042 first.
    assert {r[0] for r in rows} == {"INC-019", "INC-031", "INC-042"}
