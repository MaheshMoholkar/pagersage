"""`make seed` and `make reset`: ingest Kestrel Pay into the graph (task G03).

Reads kestrel-pay/company/*.yaml and kestrel-pay/history/export/*.jsonl (validated by
contracts/seed.py), then writes everything with MERGE on stable ids through the
backend/queries/seed_*.cypher statements. Running it twice leaves the same nodes and edges.
`reset_demo` deletes the graph and seeds it again, which also removes anything a scenario
injected (live deploys, alerts, incidents, decisions). Both finish by running the batch
algorithms (fragility, criticality, ownership gaps; task G05).
"""

import sys
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from falkordb import Graph
from redis.exceptions import ResponseError

from pagersage import embeddings, queries
from pagersage.algorithms import run_batch
from pagersage.config import REPO_ROOT
from pagersage.contracts.events import AgentEvent
from pagersage.contracts.schema import (
    commit_id,
    person_id,
    policy_id,
    postmortem_id,
    runbook_id,
    service_id,
    team_id,
)
from pagersage.contracts.seed import History, SeedBundle, load_history_dir, load_seed_dir
from pagersage.contracts.tools import live_weight
from pagersage.db import get_graph
from pagersage.indexes import ensure_indexes

COMPANY_DIR = REPO_ROOT / "kestrel-pay" / "company"
HISTORY_DIR = REPO_ROOT / "kestrel-pay" / "history" / "export"

# Seed state: every service healthy, every edge at the healthy live weight (G09), i.e. 100.
HEALTHY = 1.0
HEALTHY_WEIGHT = live_weight(HEALTHY)

# The FalkorDB image times queries out at 1000 ms; 500 rows per statement stays well under.
CHUNK = 500

Row = dict[str, Any]


def _write(graph: Graph, name: str, rows: list[Row]) -> None:
    query = queries.load(name)
    for i in range(0, len(rows), CHUNK):
        graph.query(query, {"rows": rows[i : i + CHUNK]})


def _company_rows(seed: SeedBundle, history: History) -> Iterable[tuple[str, list[Row]]]:
    services = seed.topology.services
    yield (
        "seed_services",
        [
            {
                "props": {
                    "id": service_id(s.name),
                    "name": s.name,
                    "tier": s.tier,
                    "language": s.language,
                    "description": s.description,
                    "health": HEALTHY,
                }
            }
            for s in services
        ],
    )
    yield (
        "seed_depends_on",
        [
            {
                "from": service_id(s.name),
                "to": service_id(d.to),
                "props": {
                    "calls_per_min": d.calls_per_min,
                    "p99_ms": d.p99_ms,
                    "weight": HEALTHY_WEIGHT,
                },
            }
            for s in services
            for d in s.depends_on
        ],
    )

    org = seed.org
    yield (
        "seed_teams",
        [
            {
                "props": {"id": team_id(t.slug), "name": t.name, "slack_channel": t.slack_channel},
                "owns": [service_id(s) for s in t.owns],
            }
            for t in org.teams
        ],
    )
    yield (
        "seed_people",
        [
            {
                "team": team_id(p.team),
                "props": {
                    "id": person_id(p.handle),
                    "name": p.name,
                    "handle": p.handle,
                    "timezone": p.timezone,
                    "role": p.role,
                },
            }
            for p in org.people
        ],
    )

    # One full rotation per team: the i-th person in the rota is on call for the i-th shift.
    start = datetime(*org.on_call.start.timetuple()[:3], tzinfo=UTC)
    shift = timedelta(days=org.on_call.rotation_days)
    yield (
        "seed_on_call",
        [
            {
                "person": person_id(handle),
                "team": team_id(team),
                "from": int((start + i * shift).timestamp()),
                "to": int((start + (i + 1) * shift).timestamp()),
            }
            for team, rota in org.on_call.teams.items()
            for i, handle in enumerate(rota)
        ],
    )

    # success_count / fail_count come from past incidents; best_runbook (G07) ranks on them.
    outcomes = [o for inc in history.incidents for o in inc.runbooks]
    yield (
        "seed_runbooks",
        [
            {
                "service": service_id(rb.service),
                "props": {
                    "id": runbook_id(rb.slug),
                    "title": rb.title,
                    "steps": rb.steps,
                    "success_count": sum(o.worked for o in outcomes if o.runbook == rb.slug),
                    "fail_count": sum(not o.worked for o in outcomes if o.runbook == rb.slug),
                },
            }
            for rb in seed.runbooks.runbooks
        ],
    )
    yield (
        "seed_policies",
        [
            {
                "props": {
                    "id": policy_id(p.slug),
                    "name": p.name,
                    "rule": p.rule,
                    "actions": [a.value for a in p.actions],
                    "max_tier": p.max_tier,  # None: no property, applies to every tier
                }
            }
            for p in seed.policies.policies
        ],
    )


def _history_rows(history: History) -> Iterable[tuple[str, list[Row]]]:
    yield (
        "seed_commits",
        [
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
            for c in history.commits
        ],
    )
    yield (
        "seed_deploys",
        [
            {
                "service": service_id(d.service),
                "deployed_by": person_id(d.deployed_by),
                "commits": [commit_id(sha) for sha in d.commits],
                "props": {
                    "id": d.id,
                    "version": d.version,
                    "ts": d.ts,
                    "status": d.status.value,
                    "env": d.env,
                },
            }
            for d in history.deploys
        ],
    )
    yield (
        "seed_config_changes",
        [
            {
                "service": service_id(c.service),
                "made_by": person_id(c.made_by),
                "props": {"id": c.id, "key": c.key, "old": c.old, "new": c.new, "ts": c.ts},
            }
            for c in history.config_changes
        ],
    )

    incidents = history.incidents
    yield (
        "seed_incidents",
        [
            {
                "resolved_by": person_id(i.resolved_by),
                "props": {
                    "id": i.id,
                    "title": i.title,
                    "severity": i.severity.value,
                    "status": i.status.value,
                    "opened_at": i.opened_at,
                    "resolved_at": i.resolved_at,
                    "summary": i.summary,
                },
            }
            for i in incidents
        ],
    )
    yield (
        "seed_affected",
        [{"incident": i.id, "service": service_id(s)} for i in incidents for s in i.affected],
    )
    yield (
        "seed_caused_by",
        [
            {"incident": i.id, "change": c.change, "confidence": c.confidence}
            for i in incidents
            for c in i.caused_by
        ],
    )
    yield (
        "seed_alerts",
        [
            {
                "service": service_id(a.service),
                "incident": i.id,
                "props": {
                    "id": a.id,
                    "ts": a.ts,
                    "signal": a.signal.value,
                    "value": a.value,
                    "threshold": a.threshold,
                    "severity": a.severity.value,
                },
            }
            for i in incidents
            for a in i.alerts
        ],
    )

    events = {
        i.id: [
            AgentEvent(incident_id=i.id, seq=n, ts=e.ts, kind=e.kind, summary=e.text)
            for n, e in enumerate(i.timeline, start=1)
        ]
        for i in incidents
    }
    yield ("seed_events", [{"props": e.to_node_props()} for evs in events.values() for e in evs])
    yield (
        "seed_event_chain",
        [
            {"from": a.id, "to": b.id}
            for evs in events.values()
            for a, b in zip(evs, evs[1:], strict=False)
        ],
    )

    vectors = embeddings.embed([embeddings.incident_text(i.title, i.summary) for i in incidents])
    yield (
        "seed_embeddings",
        [{"id": i.id, "embedding": v} for i, v in zip(incidents, vectors, strict=True)],
    )
    yield (
        "seed_runbook_outcomes",
        [
            {"runbook": runbook_id(o.runbook), "incident": i.id, "ts": o.ts, "worked": o.worked}
            for i in incidents
            for o in i.runbooks
        ],
    )
    yield (
        "seed_postmortems",
        [
            {
                "incident": i.id,
                "author": person_id(i.postmortem.author),
                "props": {
                    "id": postmortem_id(i.id),
                    "title": i.postmortem.title,
                    "body": i.postmortem.body,
                    "ts": i.postmortem.ts,
                },
            }
            for i in incidents
            if i.postmortem
        ],
    )


def seed_graph(
    graph: Graph, company_dir: Path = COMPANY_DIR, history_dir: Path = HISTORY_DIR
) -> dict[str, int]:
    """Validate the Kestrel Pay files, create missing indexes, MERGE everything, then run the
    batch algorithms. Returns node and edge counts by label / relationship type."""
    seed = load_seed_dir(company_dir)
    history = load_history_dir(history_dir, seed)
    ensure_indexes(graph)
    for name, rows in (*_company_rows(seed, history), *_history_rows(history)):
        _write(graph, name, rows)
    if gaps := run_batch(graph):
        print(f"Services no team owns: {', '.join(gaps)}", file=sys.stderr)
    return counts(graph)


def reset_demo(
    graph: Graph, company_dir: Path = COMPANY_DIR, history_dir: Path = HISTORY_DIR
) -> dict[str, int]:
    """Delete the graph and seed it again: the state before any scenario was injected."""
    try:
        graph.delete()
    except ResponseError as e:
        if "empty key" not in str(e):  # nothing to delete yet
            raise
    return seed_graph(graph, company_dir, history_dir)


def counts(graph: Graph) -> dict[str, int]:
    """Nodes per label and edges per relationship type, e.g. {"Service": 25, "DEPENDS_ON": 40}."""
    nodes = graph.ro_query(queries.load("count_nodes")).result_set
    edges = graph.ro_query(queries.load("count_edges")).result_set
    return dict(sorted(nodes)) | dict(sorted(edges))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    graph = get_graph()
    result = reset_demo(graph) if "--reset" in args else seed_graph(graph)
    verb = "Reset" if "--reset" in args else "Seeded"
    print(f"{verb} graph {graph.name!r}:")
    for key, n in result.items():
        print(f"  {key:<14} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
