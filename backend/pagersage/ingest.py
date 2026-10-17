"""Run-time ingest (task B10): deploys and config changes as they happen, written with the
seed loader's own statements (backend/queries/seed_*.cypher), one record at a time. MERGE on
ids, so a retried POST changes nothing.
"""

from pagersage import db, queries
from pagersage.contracts.ingest import ConfigChangeIn, DeployIn, IngestResult
from pagersage.contracts.schema import commit_id, person_id, service_id
from pagersage.contracts.tools import ToolError


def _require(graph, ids: list[str]) -> None:
    """The seed statements MATCH the service and people first, so an unknown one would make
    the write silently do nothing. Refuse it instead."""
    rows = graph.ro_query(queries.load("nodes_exist"), {"ids": ids}).result_set
    if missing := [i for i, n in rows if not n]:
        raise ToolError(f"Unknown {', '.join(missing)}: services and people must be seeded first")


def ingest_deploy(d: DeployIn) -> IngestResult:
    graph = db.get_graph()
    sid = service_id(d.service)
    _require(graph, [sid, person_id(d.deployed_by), *(person_id(c.author) for c in d.commits)])
    graph.query(
        queries.load("seed_commits"),
        {
            "rows": [
                {
                    "author": person_id(c.author),
                    "props": {
                        "id": commit_id(c.sha),
                        "sha": c.sha,
                        "message": c.message,
                        "ts": c.ts,
                        "files_changed": c.files_changed,
                        "lines_changed": c.lines_changed,
                    },
                }
                for c in d.commits
            ]
        },
    )
    graph.query(
        queries.load("seed_deploys"),
        {
            "rows": [
                {
                    "service": sid,
                    "deployed_by": person_id(d.deployed_by),
                    "commits": [commit_id(c.sha) for c in d.commits],
                    "props": {
                        "id": d.id,
                        "version": d.version,
                        "ts": d.ts,
                        "status": d.status.value,
                        "env": d.env,
                    },
                }
            ]
        },
    )
    return IngestResult(id=d.id, service_id=sid)


def ingest_config_change(c: ConfigChangeIn) -> IngestResult:
    graph = db.get_graph()
    sid = service_id(c.service)
    _require(graph, [sid, person_id(c.made_by)])
    graph.query(
        queries.load("seed_config_changes"),
        {
            "rows": [
                {
                    "service": sid,
                    "made_by": person_id(c.made_by),
                    "props": {"id": c.id, "key": c.key, "old": c.old, "new": c.new, "ts": c.ts},
                }
            ]
        },
    )
    return IngestResult(id=c.id, service_id=sid)
