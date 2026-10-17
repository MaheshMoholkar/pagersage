"""Facts about FalkorDB 6.0.2 that the plan and contracts rely on. If an image upgrade breaks
one of these, fix docs/contracts.md and the queries before bumping the tag."""

import importlib.util
from pathlib import Path

# Names as the build plan writes them; FalkorDB matches procedure names case-insensitively.
REQUIRED_PROCEDURES = {
    "algo.bfs",
    "algo.sppaths",
    "algo.sspaths",
    "algo.betweenness",
    "algo.pagerank",
    "algo.labelpropagation",
    "algo.wcc",
    "db.idx.vector.querynodes",
    "db.idx.fulltext.querynodes",
}


def test_required_procedures_exist(graph):
    rows = graph.query("CALL dbms.procedures() YIELD name RETURN name").result_set
    names = {r[0].lower() for r in rows}
    assert names >= REQUIRED_PROCEDURES, f"missing: {sorted(REQUIRED_PROCEDURES - names)}"


def test_lowercase_procedure_names_work(graph):
    graph.query("CREATE (:S {id:'a'})-[:D]->(:S {id:'b'})")
    rows = graph.query(
        "MATCH (s:S {id:'a'}) CALL algo.bfs(s, 3, 'D') YIELD nodes RETURN size(nodes)"
    ).result_set
    assert rows == [[1]]


def test_bfs_excludes_start_node(graph):
    # blast_radius (G07) relies on this: the alerting service is not in its own blast radius.
    graph.query("CREATE (:S {id:'a'})-[:D]->(:S {id:'b'})-[:D]->(:S {id:'c'})")
    rows = graph.query(
        "MATCH (s:S {id:'a'}) CALL algo.BFS(s, 3, 'D') YIELD nodes RETURN [n IN nodes | n.id]"
    ).result_set
    assert rows == [[["b", "c"]]]


def test_line_comments_are_allowed_in_queries(graph):
    rows = graph.query("// what this answers\n// params: none\nRETURN 1 AS one").result_set
    assert rows == [[1]]


def test_params_are_bound_not_formatted(graph):
    graph.query("CREATE (:S {id:$id})", {"id": "x' OR 1=1"})
    rows = graph.query("MATCH (s:S {id:$id}) RETURN count(s)", {"id": "x' OR 1=1"}).result_set
    assert rows == [[1]]


def _load_smoke_algos():
    path = Path(__file__).resolve().parents[2] / "scripts" / "smoke_algos.py"
    spec = importlib.util.spec_from_file_location("smoke_algos", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_algos(graph):
    # scripts/smoke_algos.py (G01): every procedure the plan uses, plus vector score direction,
    # fractional pathWeight, SSpaths pathCount and full-text fuzzy syntax.
    failed = [(name, finding) for name, ok, finding in _load_smoke_algos().run(graph) if not ok]
    assert not failed, failed


def test_smoke_algos_failure_does_not_stop_later_checks(graph):
    smoke = _load_smoke_algos()

    def no_rows(g):
        [[_]] = []  # what a check sees when a procedure suddenly returns nothing: ValueError

    checks = [("broken", no_rows), ("next", lambda g: "ran")]
    assert [(n, ok) for n, ok, _ in smoke.run(graph, checks)] == [("broken", False), ("next", True)]


def test_pattern_comprehensions_without_relationship_variables_combine(graph):
    # FalkorDB 6.0.2 bug: a comprehension that binds a relationship variable, e.g.
    # [(a)-[r:R]->(i) WHERE r.ok | ...], empties the comprehensions after it (and sometimes
    # itself). Bind no relationship variables in comprehensions; use OPTIONAL MATCH + collect
    # when an edge property is needed (similar_incidents, G12).
    graph.query("CREATE (i:I), (:A {v:1})-[:R {ok:true}]->(i), (:B {t:'x'})-[:S]->(i)")
    rows = graph.query(
        "MATCH (i:I) RETURN [(a:A)-[:R]->(i) | a.v], [(b:B)-[:S]->(i) | b.t]"
    ).result_set
    assert rows == [[[1], ["x"]]]
