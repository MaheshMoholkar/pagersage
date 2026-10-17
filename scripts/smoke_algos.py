"""Call every FalkorDB procedure PagerSage relies on once, against a throwaway toy graph (G01).

The FalkorDB docs disagree with themselves on some names and leave two behaviours open, so this
fails in minute 5 instead of days later. It also answers the two open questions (build-plan.md
section 1):

- vector `score` direction: similarity (higher = closer) or distance (lower = closer)?
- does `algo.SPpaths` keep fractional `weightProp` values in `pathWeight`?

Run with FalkorDB up (`make db`): `make smoke`. CI runs the same checks in tests/test_falkordb.py.
Exit code 0 when every check passes. Never touches the real `pagersage` graph.
"""

import contextlib
import math
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from falkordb import Graph  # noqa: E402
from redis.exceptions import RedisError  # noqa: E402

from pagersage import db  # noqa: E402

# Toy topology, a calls b (DEPENDS_ON). Two routes from a to c: via b (cheap) and via d (dear).
#   a -1-> b -1-> c        weight (int) on every edge, fw (float) for the fractional check
#   a -5-> d -5-> c
#   e: isolated, so wcc sees two components
TOY = """
CREATE (a:Service {id:'a', name:'checkout-api', description:'takes the order'}),
       (b:Service {id:'b', name:'payments-svc', description:'charges the card'}),
       (c:Service {id:'c', name:'payments-db', description:'postgres for payments'}),
       (d:Service {id:'d', name:'fraud-svc', description:'scores the order'}),
       (e:Service {id:'e', name:'email-svc', description:'sends receipts'}),
       (a)-[:DEPENDS_ON {weight:1, fw:0.5}]->(b),
       (b)-[:DEPENDS_ON {weight:1, fw:0.25}]->(c),
       (a)-[:DEPENDS_ON {weight:5, fw:2.5}]->(d),
       (d)-[:DEPENDS_ON {weight:5, fw:2.5}]->(c)
"""

Check = Callable[[Graph], str]
CHECKS: list[tuple[str, Check]] = []


def check(name: str) -> Callable[[Check], Check]:
    """Register a check. It returns a one-line finding, or raises AssertionError/RedisError."""

    def register(fn: Check) -> Check:
        CHECKS.append((name, fn))
        return fn

    return register


def rows(g: Graph, q: str, params: dict | None = None) -> list[list]:
    return g.query(q, params).result_set


@check("algo.bfs")
def bfs(g: Graph) -> str:
    [[ids]] = rows(
        g,
        "MATCH (s:Service {id:'a'}) CALL algo.bfs(s, 3, 'DEPENDS_ON') YIELD nodes "
        "RETURN [n IN nodes | n.id]",
    )
    assert sorted(ids) == ["b", "c", "d"], ids
    return f"reached {sorted(ids)}, start node excluded"


@check("algo.SPpaths")
def sppaths(g: Graph) -> str:
    [[ids, weight]] = rows(
        g,
        "MATCH (a:Service {id:'a'}), (c:Service {id:'c'}) "
        "CALL algo.SPpaths({sourceNode:a, targetNode:c, relTypes:['DEPENDS_ON'], "
        "relDirection:'outgoing', weightProp:'weight', pathCount:1}) "
        "YIELD path, pathWeight RETURN [n IN nodes(path) | n.id], pathWeight",
    )
    assert ids == ["a", "b", "c"], ids
    assert weight == 2, weight
    return f"cheapest path {ids}, pathWeight {weight!r} ({type(weight).__name__})"


@check("algo.SPpaths fractional weightProp")
def sppaths_float(g: Graph) -> str:
    [[ids, weight]] = rows(
        g,
        "MATCH (a:Service {id:'a'}), (c:Service {id:'c'}) "
        "CALL algo.SPpaths({sourceNode:a, targetNode:c, relTypes:['DEPENDS_ON'], "
        "relDirection:'outgoing', weightProp:'fw', pathCount:1}) "
        "YIELD path, pathWeight RETURN [n IN nodes(path) | n.id], pathWeight",
    )
    assert ids == ["a", "b", "c"], ids
    assert abs(weight - 0.75) < 1e-6, f"fractions lost: pathWeight {weight!r}"
    return f"0.5 + 0.25 -> pathWeight {weight!r}: fractions kept"


@check("algo.SSpaths pathCount is a total, not per target")
def sspaths_path_count(g: Graph) -> str:
    # The plan's T3 used pathCount:1 expecting one path per reachable node. It is one path
    # in total (the cheapest), so T3 would only ever see the nearest dependency.
    result = rows(
        g,
        "MATCH (a:Service {id:'a'}) "
        "CALL algo.SSpaths({sourceNode:a, relTypes:['DEPENDS_ON'], relDirection:'outgoing', "
        "weightProp:'weight', maxLen:4, pathCount:1}) "
        "YIELD path RETURN [n IN nodes(path) | n.id]",
    )
    assert result == [[["a", "b"]]], result
    return "pathCount:1 -> one path overall"


@check("algo.SSpaths distance per target")
def sspaths(g: Graph) -> str:
    # What T3 needs instead: a generous pathCount, then the cheapest path per target.
    result = rows(
        g,
        "MATCH (a:Service {id:'a'}) "
        "CALL algo.SSpaths({sourceNode:a, relTypes:['DEPENDS_ON'], relDirection:'outgoing', "
        "weightProp:'weight', maxLen:4, pathCount:1000}) "
        "YIELD path, pathWeight RETURN last(nodes(path)).id, min(pathWeight)",
    )
    dist = dict(result)
    assert dist == {"b": 1, "c": 2, "d": 5}, dist
    return f"pathCount:1000 + min(pathWeight): {dict(sorted(dist.items()))}"


@check("algo.betweenness")
def betweenness(g: Graph) -> str:
    result = rows(
        g,
        "CALL algo.betweenness({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON'], "
        "samplingSize:100, samplingSeed:42}) YIELD node, score RETURN node.id, score",
    )
    score = dict(result)
    # b and d each sit on one a->c route; the source and the sink sit on none.
    assert score["b"] > 0 and score["d"] > 0, score
    assert score["a"] == 0 and score["c"] == 0, score
    return f"scores {dict(sorted(score.items()))}"


@check("algo.pageRank")
def pagerank(g: Graph) -> str:
    result = rows(
        g, "CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score RETURN node.id, score"
    )
    score = dict(result)
    top = max(score, key=score.get)
    assert top == "c", score  # everything ends up calling payments-db
    return f"top node {top!r} ({score[top]:.3f})"


@check("algo.labelPropagation")
def label_propagation(g: Graph) -> str:
    result = rows(
        g,
        "CALL algo.labelPropagation({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON'], "
        "maxIterations:10}) YIELD node, communityId RETURN node.id, communityId",
    )
    community = dict(result)
    assert set(community) == {"a", "b", "c", "d", "e"}, community
    assert community["e"] != community["a"], community
    return f"{len(set(community.values()))} communities"


@check("algo.wcc")
def wcc(g: Graph) -> str:
    result = rows(
        g,
        "CALL algo.wcc({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON']}) "
        "YIELD node, componentId RETURN node.id, componentId",
    )
    component = dict(result)
    assert len({component[n] for n in "abcd"}) == 1, component
    assert component["e"] != component["a"], component
    return "2 components (a-d connected, e alone)"


@check("db.idx.vector.queryNodes + score direction")
def vector(g: Graph) -> str:
    g.query(
        "CREATE VECTOR INDEX FOR (i:Incident) ON (i.embedding) "
        "OPTIONS {dimension:3, similarityFunction:'cosine'}"
    )
    g.query(
        "CREATE (:Incident {id:'same', embedding:vecf32([1.0, 0.0, 0.0])}), "
        "(:Incident {id:'near', embedding:vecf32([0.9, 0.1, 0.0])}), "
        "(:Incident {id:'opposite', embedding:vecf32([-1.0, 0.0, 0.0])})"
    )
    result = rows(
        g,
        "CALL db.idx.vector.queryNodes('Incident', 'embedding', 3, vecf32($v)) "
        "YIELD node, score RETURN node.id, score",
        {"v": [1.0, 0.0, 0.0]},
    )
    score = dict(result)
    assert set(score) == {"same", "near", "opposite"}, score
    assert [r[0] for r in result] == ["same", "near", "opposite"], result  # nearest first
    # score is cosine DISTANCE (0 = same, 2 = opposite), not similarity: rank ascending, or
    # use 1 - score as the similarity.
    # Check the values too, not just the order: G12 turns them into 1 - score and adds a graph
    # bonus, so a changed scale would quietly change the ranking.
    expected = {"same": 0.0, "near": 1 - 0.9 / math.sqrt(0.82), "opposite": 2.0}  # near: 0.006116
    for k, want in expected.items():
        assert math.isclose(score[k], want, abs_tol=1e-4), (k, score[k], want)
    shown = {k: round(v, 3) for k, v in score.items()}
    return f"score is a distance (lower = closer): {shown}"


@check("db.idx.fulltext.queryNodes")
def fulltext(g: Graph) -> str:
    g.query("CREATE FULLTEXT INDEX FOR (s:Service) ON (s.name, s.description)")
    query = "CALL db.idx.fulltext.queryNodes('Service', $q) YIELD node RETURN node.id"
    found = {q: {r[0] for r in rows(g, query, {"q": q})} for q in ("pay*", "%paymnts%")}
    # %term% is fuzzy at edit distance 1. The plan's '%paymnts%1' matches nothing.
    assert found == {"pay*": {"b", "c"}, "%paymnts%": {"b", "c"}}, found
    return "'pay*' and fuzzy '%paymnts%' -> ['b', 'c']"


def run(g: Graph, checks: list[tuple[str, Check]] | None = None) -> list[tuple[str, bool, str]]:
    """Seed the toy graph into `g` and run every check. Returns (name, passed, finding).

    Any exception fails only its own check (an unexpected row shape raises ValueError or
    KeyError, not AssertionError), so one broken procedure never hides the rest."""
    g.query(TOY)
    results = []
    for name, fn in checks or CHECKS:
        try:
            results.append((name, True, fn(g)))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))
    return results


def main() -> int:
    g = db.get_db().select_graph(f"smoke_{uuid.uuid4().hex[:12]}")
    try:
        results = run(g)
    finally:
        with contextlib.suppress(RedisError):
            g.delete()
    width = max(len(name) for name, _, _ in results)
    for name, ok, finding in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {finding}")
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
