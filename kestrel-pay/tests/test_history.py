"""History export (task K5): reproducible, internally consistent, and carrying the four planted
patterns the demo depends on (PLAN.md section 2)."""

import json
from collections import Counter, defaultdict, deque

import pytest
import yaml
from conftest import ROOT, load_script

generate = load_script("history/generate.py")
EXPORT = ROOT / "history" / "export"
POOL_RUNBOOK = "raise-payments-db-pool"


@pytest.fixture(scope="module")
def history() -> dict[str, list[dict]]:
    return {
        name: [json.loads(line) for line in (EXPORT / f"{name}.jsonl").read_text().splitlines()]
        for name in ("deploys", "commits", "config_changes", "incidents")
    }


@pytest.fixture(scope="module")
def topology() -> list[dict]:
    return yaml.safe_load((ROOT / "company" / "topology.yaml").read_text())["services"]


def _texts(incident: dict) -> list[str]:
    pm = incident["postmortem"]
    return [incident["title"], incident["summary"], pm["title"], pm["body"]] + [
        e["text"] for e in incident["timeline"]
    ]


# ── reproducible and consistent ───────────────────────────────────────────


def test_same_seed_gives_the_committed_bytes():
    for name, text in generate.render().items():
        assert (EXPORT / name).read_text(encoding="utf-8") == text, (
            f"{name} is stale: run history/generate.py"
        )


def test_volumes(history):
    assert 380 <= len(history["deploys"]) <= 440
    assert 1350 <= len(history["commits"]) <= 1700
    assert len(history["config_changes"]) == generate.CONFIG_CHANGES
    assert [i["id"] for i in history["incidents"]] == [f"INC-{n:03d}" for n in range(11, 51)]


def test_everything_inside_the_window(history):
    stamps = [r["ts"] for name in ("deploys", "commits", "config_changes") for r in history[name]]
    stamps += [i["postmortem"]["ts"] for i in history["incidents"]]
    assert min(stamps) >= generate.START_TS
    assert max(stamps) < generate.END_TS


def test_text_is_fully_rendered(history):
    for inc in history["incidents"]:
        for text in _texts(inc):
            assert "{" not in text and "}" not in text, f"{inc['id']}: {text[:80]}"


def test_config_history_ends_at_config_yaml(history):
    chains: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in history["config_changes"]:
        chains[(c["service"], c["key"])].append(c)
    for (service, key), chain in chains.items():
        for before, after in zip(chain, chain[1:], strict=False):
            assert before["new"] == after["old"], f"{service}.{key}: {before['id']}->{after['id']}"
        current = yaml.safe_load((ROOT / "services" / service / "config.yaml").read_text())[key]
        assert chain[-1]["new"] == generate.fmt(current), f"{service}.{key} ends off config.yaml"


def test_runbook_outcomes_line_up_with_the_timeline(history):
    for inc in history["incidents"]:
        stamps = {e["ts"] for e in inc["timeline"]}
        for r in inc["runbooks"]:
            assert r["ts"] in stamps, f"{inc['id']}: {r['runbook']} has no timeline entry"


# ── planted patterns ──────────────────────────────────────────────────────


def _pool_cut(change: dict) -> bool:
    return (
        change["service"] == "payments-db"
        and change["key"] == "max_pool_size"
        and int(change["new"]) < int(change["old"])
    )


def test_pattern1_pool_incidents_and_their_runbook(history):
    changes = {c["id"]: c for c in history["config_changes"]}
    pool = [
        i
        for i in history["incidents"]
        if any(c["change"] in changes and _pool_cut(changes[c["change"]]) for c in i["caused_by"])
    ]
    assert [i["id"] for i in pool] == ["INC-019", "INC-031", "INC-042"]
    for inc in pool:
        assert set(inc["affected"]) >= {"checkout-api", "payments-svc", "payments-db"}
        assert {(a["service"], a["signal"]) for a in inc["alerts"]} >= {
            ("checkout-api", "error_rate")
        }
    outcomes = [
        (i["id"], r["worked"])
        for i in history["incidents"]
        for r in i["runbooks"]
        if r["runbook"] == POOL_RUNBOOK
    ]
    assert outcomes == [("INC-019", True), ("INC-031", True), ("INC-042", True)]
    # Every pool cut in history caused one of these incidents.
    cuts = [c["id"] for c in history["config_changes"] if _pool_cut(c)]
    assert cuts == [i["caused_by"][0]["change"] for i in pool]


def test_pattern2_ledger_svc_has_one_author(history):
    author = {c["sha"]: c["author"] for c in history["commits"]}
    authors: dict[str, set[str]] = defaultdict(set)
    for d in history["deploys"]:
        authors[d["service"]].update(author[sha] for sha in d["commits"])
    assert authors.pop("ledger-svc") == {"ines"}
    thin = sorted(svc for svc, people in authors.items() if len(people) < 2)
    assert not thin, f"only ledger-svc may have a single author: {thin}"


def _betweenness(services: list[dict]) -> dict[str, float]:
    """Brandes on the directed, unweighted DEPENDS_ON graph (what algo.betweenness computes)."""
    names = [s["name"] for s in services]
    out = {s["name"]: [d["to"] for d in s.get("depends_on", [])] for s in services}
    score = dict.fromkeys(names, 0.0)
    for src in names:
        order, preds = [], {n: [] for n in names}
        paths, dist = dict.fromkeys(names, 0), dict.fromkeys(names, -1)
        paths[src], dist[src] = 1, 0
        queue = deque([src])
        while queue:
            v = queue.popleft()
            order.append(v)
            for w in out[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    paths[w] += paths[v]
                    preds[w].append(v)
        delta = dict.fromkeys(names, 0.0)
        for w in reversed(order):
            for v in preds[w]:
                delta[v] += paths[v] / paths[w] * (1 + delta[w])
            if w != src:
                score[w] += delta[w]
    return score


def test_pattern3_kafka_is_most_fragile(topology):
    ranked = sorted(_betweenness(topology).items(), key=lambda kv: -kv[1])
    assert ranked[0][0] == "kafka"
    assert ranked[0][1] > 1.5 * ranked[1][1], f"kafka should win clearly: {ranked[:3]}"


def test_pattern4_noisy_checkout_and_its_decoy_deploys(history):
    deploys = history["deploys"]
    busiest = Counter(d["service"] for d in deploys).most_common(2)
    assert busiest[0][0] == "checkout-api"
    for iid in ("INC-031", "INC-042"):
        inc = next(i for i in history["incidents"] if i["id"] == iid)
        latest = max((d for d in deploys if d["ts"] < inc["opened_at"]), key=lambda d: d["ts"])
        assert latest["service"] == "checkout-api"
        assert inc["opened_at"] - latest["ts"] <= 10 * 60
        assert latest["id"] not in {c["change"] for c in inc["caused_by"]}
