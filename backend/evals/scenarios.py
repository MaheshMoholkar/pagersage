"""Scenario evals (task A12): Kestrel Pay's scenarios end to end, with real Claude calls.

    make eval                          # all three scenarios
    make eval SCENARIO=redis-down      # one
    cd backend && uv run python -m evals.scenarios redis-down --keep

Each scenario gets a fresh throwaway graph seeded with Kestrel Pay. Its steps go through the
real API in-process: kestrel-pay/scenarios/inject.py runs with its HTTP call sent to the app
and git replaced (no branch, no server). Then the orchestrator runs the pipeline on the
incident, the incident is resolved, and the Scribe runs. Discord and GitHub calls are recorded,
never sent.

A scenario passes when the incident's top CAUSED_BY is the scenario's `expect.cause`. The other
expectations are reported alongside: the decoy not blamed, the path, the precedents linked,
the runbook picked and its count, the team paged, and the postmortem written.

Real API calls cost money: run this by hand with ANTHROPIC_API_KEY set, never in CI.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from types import ModuleType
from typing import Any

os.environ["AGENTS_ENABLED"] = "false"  # the eval starts the agents itself, after every step

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pagersage import db, seed  # noqa: E402
from pagersage.agents import orchestrator  # noqa: E402
from pagersage.config import REPO_ROOT, get_settings  # noqa: E402
from pagersage.contracts import tools  # noqa: E402
from pagersage.contracts.schema import person_id, runbook_id, service_id, team_id  # noqa: E402
from pagersage.main import app  # noqa: E402

KESTREL = REPO_ROOT / "kestrel-pay"
SCENARIOS = ("pool-exhaustion", "redis-down", "inventory-slow")
NOW = 1_792_500_000  # after Kestrel Pay's history ends, inside the on-call rota


def load_inject() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kestrel_inject", KESTREL / "scenarios" / "inject.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NoGit:
    """inject.py's Git without git: files come from the working tree, commit shas are made up."""

    head = "HEAD"

    def show(self, rev: str, file: str) -> str | None:
        path = KESTREL / file
        return path.read_text(encoding="utf-8") if path.exists() else None

    def commit(self, parent: str, file: str, content: str, message: str, who: dict, ts: int):
        return hashlib.sha1(f"{parent}:{file}:{message}:{ts}".encode()).hexdigest()

    def run(self, *args: Any, **kwargs: Any) -> str:
        return ""


def recorder(sent: list[str]):
    """Stands in for httpx.post in the action tools: Discord 204, GitHub 201."""

    def post(url, json, timeout, headers=None):
        sent.append(url)
        if "github" in url:
            return httpx.Response(201, json={"html_url": "https://github.com/eval/eval/issues/1"})
        return httpx.Response(204)

    return post


def rows(graph, query: str, **params: Any) -> list:
    return graph.ro_query(query, params).result_set


def check(graph, iid: str, sc: Any, made: dict[str, str], before: list) -> dict[str, Any]:
    exp = sc.expect
    causes = rows(
        graph,
        "MATCH (:Incident {id:$i})-[c:CAUSED_BY]->(x) RETURN x.id ORDER BY c.confidence DESC",
        i=iid,
    )
    [[status, state]] = rows(graph, "MATCH (i:Incident {id:$i}) RETURN i.status, i.state", i=iid)
    state = json.loads(state or "{}")
    similar = {r[0] for r in rows(graph, "MATCH (:Incident {id:$i})-[:SIMILAR_TO]->(o) "
                                         "RETURN o.id", i=iid)}  # fmt: skip
    paged = [
        r[0]
        for r in rows(
            graph,
            "MATCH (e:Event {incident_id:$i, kind:'action'}) RETURN e.data ORDER BY e.seq",
            i=iid,
        )
    ]
    handles = [d["handle"] for d in map(json.loads, paged) if d.get("handle")]
    teams = {
        r[0]
        for r in rows(
            graph,
            "MATCH (p:Person)-[:MEMBER_OF]->(t:Team) WHERE p.id IN $p RETURN t.id",
            p=[person_id(h) for h in handles],
        )
    }
    rb = runbook_id(exp["runbook"])
    [after] = rows(graph, "MATCH (rb:Runbook {id:$rb}) RETURN rb.success_count", rb=rb)
    postmortem = rows(graph, "MATCH (pm:Postmortem)-[:ABOUT]->(:Incident {id:$i}) "
                             "RETURN pm.title", i=iid)  # fmt: skip
    cause, decoy = made[exp["cause"]], made[exp["decoy"]]
    return {
        "PASS cause": bool(causes) and causes[0][0] == cause,
        "cause": f"{causes[0][0] if causes else None} (want {cause})",
        "decoy not blamed": decoy not in [c[0] for c in causes[:1]],
        "path": state.get("path") == [service_id(s) for s in exp["path"]],
        "similar": f"{sorted(similar)} (want {exp['similar']})",
        "runbook": f"{state.get('runbook')} (want {rb}); success {before[0]} -> {after[0]}",
        "paged team": team_id(exp["page_team"]) in teams,
        "paged": handles,
        "postmortem": postmortem[0][0] if postmortem else None,
        "status": status,
    }


def run_scenario(name: str, keep: bool = False) -> dict[str, Any]:
    inject = load_inject()
    sc = inject.load_scenario(name)
    graph = db.get_db().select_graph(f"eval_{name.replace('-', '_')}_{uuid.uuid4().hex[:8]}")
    sent: list[str] = []
    settings = get_settings()
    settings.discord_webhook_url = "https://discord.invalid/eval"
    settings.github_token, settings.github_issues_repo = "eval", "eval/eval"
    db.get_graph = lambda name=None: graph  # every tool and route reads this graph
    tools._now = lambda: NOW
    tools._post = recorder(sent)
    try:
        seed.seed_graph(graph)
        client = TestClient(app)
        inject.post = lambda api, path, body: client.post(path, json=body).status_code
        inject._git = lambda repo: NoGit()
        made = inject.run(sc, api="in-process", repo=None, pause=False, now=NOW)
        incidents = rows(graph, "MATCH (i:Incident) WHERE i.opened_at >= $t "
                                "RETURN i.id ORDER BY i.id", t=NOW - 3600)  # fmt: skip
        iid = incidents[0][0]
        before = rows(graph, "MATCH (rb:Runbook {id:$rb}) RETURN rb.success_count",
                      rb=runbook_id(sc.expect["runbook"]))[0]  # fmt: skip
        started = time.monotonic()
        orchestrator.run_pipeline(iid)
        tools.resolve_incident(iid, f"Ran the {sc.expect['runbook']} runbook; service recovered.")
        orchestrator.run_scribe(iid)
        result = check(graph, iid, sc, made, before)
        result["incident"] = f"{iid} ({len(incidents)} opened)"
        result["seconds"] = round(time.monotonic() - started)
        result["actions sent"] = len(sent)
        return result
    finally:
        if keep:
            print(f"kept graph {graph.name}")
        else:
            graph.delete()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Kestrel Pay scenarios through the agents.")
    ap.add_argument("scenarios", nargs="*", default=list(SCENARIOS))
    ap.add_argument("--keep", action="store_true", help="keep each eval graph for inspection")
    args = ap.parse_args(argv)
    if not get_settings().anthropic_api_key:
        print("evals: set ANTHROPIC_API_KEY (real API calls; this costs money)", file=sys.stderr)
        return 2
    failed = 0
    for name in args.scenarios:
        print(f"\n== {name}")
        result = run_scenario(name, keep=args.keep)
        failed += not result["PASS cause"]
        for key, value in result.items():
            print(f"  {key:18} {value}")
    print(f"\n{len(args.scenarios) - failed}/{len(args.scenarios)} scenarios found the cause")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
