"""Indexes and constraints (task G02; build-plan.md sections 1 and 3).

`ensure_indexes(graph)` is idempotent: it reads what the graph already has and creates only
what is missing, so the seed loader, `make reset` and tests can all call it. FalkorDB raises
"already indexed" on a repeated CREATE INDEX, which is why this diffs instead of retrying.

Run it on its own with `make indexes`.
"""

import sys
import time

from falkordb import Graph
from redis.exceptions import ResponseError

from pagersage.contracts.schema import Label
from pagersage.db import get_graph

# all-MiniLM-L6-v2 (G04) writes 384-dim vectors. Vector search returns cosine distance.
EMBEDDING_DIM = 384
SIMILARITY = "cosine"

# Every node has a unique `id`. Commit.id is the sha, but `sha` is indexed too for ingest lookups.
UNIQUE: tuple[tuple[Label, str], ...] = tuple((label, "id") for label in Label)
RANGE: tuple[tuple[Label, str], ...] = (*UNIQUE, (Label.COMMIT, "sha"))
FULLTEXT: tuple[tuple[Label, str], ...] = ((Label.SERVICE, "name"), (Label.SERVICE, "description"))
VECTOR: tuple[Label, str] = (Label.INCIDENT, "embedding")


class IndexSetupError(RuntimeError):
    """The graph has an index or constraint that conflicts with the one PagerSage needs."""


def _indexes(graph: Graph) -> dict[tuple[str, str, str], dict]:
    """(label, property, type) -> options, for every node index the graph has."""
    try:
        result = graph.call_procedure("db.indexes")
    except ResponseError as e:
        if "empty key" in str(e):  # the graph does not exist yet
            return {}
        raise
    cols = [name for _, name in result.header]
    found = {}
    for row in result.result_set:
        r = dict(zip(cols, row, strict=True))
        if r["entitytype"] != "NODE":
            continue
        for prop, types in r["types"].items():
            for t in types:
                found[(r["label"], prop, t)] = dict(r["options"].get(prop) or {})
    return found


def _unique_constraints(graph: Graph) -> dict[tuple[str, str], str]:
    """(label, property) -> status, for every single-property unique node constraint."""
    return {
        (c["label"], c["properties"][0]): c["status"]
        for c in graph.list_constraints()
        if c["type"] == "UNIQUE" and c["entitytype"] == "NODE" and len(c["properties"]) == 1
    }


def _check_vector(options: dict) -> None:
    label, prop = VECTOR
    got = (options.get("dimension"), options.get("similarityFunction"))
    if got != (EMBEDDING_DIM, SIMILARITY):
        raise IndexSetupError(
            f"Vector index {label}.{prop} has dimension {got[0]}, {got[1]}; PagerSage needs "
            f"dimension {EMBEDDING_DIM}, {SIMILARITY}. Drop it "
            f"(DROP VECTOR INDEX FOR (n:{label}) ON (n.{prop})) and run `make indexes` again."
        )


def _wait_operational(graph: Graph, timeout: float) -> None:
    """Unique constraints build asynchronously (PENDING -> OPERATIONAL or FAILED)."""
    deadline = time.monotonic() + timeout
    while True:
        status = _unique_constraints(graph)
        failed = sorted(f"{lbl}.{p}" for (lbl, p), s in status.items() if s == "FAILED")
        if failed:
            raise IndexSetupError(
                f"Unique constraint failed on {', '.join(failed)}: the graph already has "
                "duplicate ids. Fix the data (or `make reset`) and run `make indexes` again."
            )
        if all(status.get(key) == "OPERATIONAL" for key in UNIQUE):
            return
        if time.monotonic() > deadline:
            raise IndexSetupError(f"Unique constraints still pending after {timeout}s")
        time.sleep(0.05)


def ensure_indexes(graph: Graph, timeout: float = 10.0) -> list[str]:
    """Create every missing index and unique constraint, then wait until the constraints are
    enforced. Returns what was created (empty when the graph was already set up)."""
    have = _indexes(graph)
    created = []

    for label, prop in RANGE:
        if (label, prop, "RANGE") not in have:
            graph.create_node_range_index(label, prop)
            created.append(f"range {label}.{prop}")

    for label, prop in FULLTEXT:
        if (label, prop, "FULLTEXT") not in have:
            graph.create_node_fulltext_index(label, prop)  # adds a field to the label's index
            created.append(f"fulltext {label}.{prop}")

    label, prop = VECTOR
    if (label, prop, "VECTOR") in have:
        _check_vector(have[(label, prop, "VECTOR")])
    else:
        graph.create_node_vector_index(
            label, prop, dim=EMBEDDING_DIM, similarity_function=SIMILARITY
        )
        created.append(f"vector {label}.{prop}")

    constraints = _unique_constraints(graph)
    for label, prop in UNIQUE:
        if (label, prop) not in constraints:
            # The range index already exists (created above), so this only adds the constraint.
            graph.create_node_unique_constraint(label, prop)
            created.append(f"unique {label}.{prop}")

    _wait_operational(graph, timeout)
    return created


def main(argv: list[str] | None = None) -> int:
    graph = get_graph()
    try:
        created = ensure_indexes(graph)
    except IndexSetupError as e:
        print(e, file=sys.stderr)
        return 1
    if created:
        print(f"Graph {graph.name!r}: created {len(created)}:")
        for item in created:
            print(f"  {item}")
    else:
        print(f"Graph {graph.name!r}: every index and constraint already exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
