"""Scenarios and the injector (tasks K7, K8)."""

import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml
from conftest import ROOT, load_script

inject = load_script("scenarios/inject.py")
NAMES = sorted(p.stem for p in (ROOT / "scenarios").glob("*.yaml"))
NOW = 1_792_000_000


def test_three_scenarios():
    assert NAMES == ["inventory-slow", "pool-exhaustion", "redis-down"]


@pytest.mark.parametrize("name", NAMES)
def test_scenario_is_consistent(name):
    sc = inject.load_scenario(name)
    e = sc.expect
    cause, decoy = sc.step(e["cause"]), sc.step(e["decoy"])
    assert cause.spec["service"] == e["root_service"]
    assert e["path"][0] == e["alerting_service"] and e["path"][-1] == e["root_service"]
    # The decoy is the latest deploy before the first alert, so "blame the latest deploy" is
    # wrong; it is on a different service than the cause.
    deploys = [s for s in sc.steps if s.kind == "deploy" and s.at < 0]
    assert max(deploys, key=lambda s: s.at).name == decoy.name
    assert decoy.spec["service"] != e["root_service"]


def test_pool_exhaustion_repeats_the_planted_pattern():
    sc = inject.load_scenario("pool-exhaustion")
    cut = sc.step("pool-cut").spec
    assert (cut["service"], cut["key"]) == ("payments-db", "max_pool_size")
    config = yaml.safe_load((ROOT / "services" / "payments-db" / "config.yaml").read_text())
    assert cut["to"] < config["max_pool_size"]
    assert sc.step("payments-deploy").spec["service"] == "payments-svc"
    assert sc.step("checkout-deploy").spec["service"] == "checkout-api"
    assert sc.expect["similar"][0] == "INC-042"


def test_unknown_scenario_is_a_clear_error():
    with pytest.raises(ValueError, match="No scenario 'nope'; known: \\["):
        inject.load_scenario("nope")


# ── end to end: scratch repo + stub PagerSage ─────────────────────────────


class _Stub(BaseHTTPRequestHandler):
    calls: list[tuple[str, dict]]
    status = 202

    def do_POST(self):  # noqa: N802 (http.server API)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append((self.path, body))
        self.send_response(self.status)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def stub():
    handler = type("Handler", (_Stub,), {"calls": [], "status": 202})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield handler, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


@pytest.fixture
def repo(tmp_path):
    """A git repo laid out like this one, holding just the files the scenario touches."""
    for svc in ("payments-db", "checkout-api"):
        dst = tmp_path / "kestrel-pay" / "services" / svc
        dst.mkdir(parents=True)
        shutil.copy(ROOT / "services" / svc / "config.yaml", dst / "config.yaml")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_pool_exhaustion_end_to_end(repo, stub):
    handler, url = stub
    head = _git(repo, "rev-parse", "HEAD")
    made = inject.run(
        inject.load_scenario("pool-exhaustion"), api=url, repo=repo, pause=False, now=NOW
    )

    paths = [p for p, _ in handler.calls]
    assert paths == ["/ingest/deploy", "/ingest/config-change", "/ingest/deploy", "/alerts",
                     "/alerts"]  # fmt: skip
    bad_deploy, change, decoy = (b for _, b in handler.calls[:3])
    assert change == {"id": "cfg-0061", "service": "payments-db", "key": "max_pool_size",
                      "old": "200", "new": "60", "ts": NOW - 360, "made_by": "tomas"}  # fmt: skip
    assert bad_deploy["service"] == "payments-svc" and bad_deploy["id"] == "dep-0416"
    assert decoy["service"] == "checkout-api" and decoy["ts"] > bad_deploy["ts"]

    # The bad commit is real, on its own branch, and changed only the pool size.
    sha = bad_deploy["commits"][0]["sha"]
    assert sha == made["pool-commit"]
    shown = _git(repo, "show", f"{sha}:kestrel-pay/services/payments-db/config.yaml")
    assert "max_pool_size: 60" in shown and "statement_timeout_ms: 5000" in shown
    assert (
        _git(repo, "log", "-1", "--format=%an <%ae>", sha)
        == "Tomás Ortega <tomas@kestrelpay.example>"
    )
    branch = _git(
        repo, "branch", "--list", "incident/pool-exhaustion-*", "--format=%(refname:short)"
    )
    assert _git(repo, "rev-parse", branch) == made["checkout-commit"]
    assert _git(repo, "rev-parse", f"{made['checkout-commit']}^") == sha

    # The working tree and current branch are untouched.
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "status", "--porcelain") == ""

    alert = handler.calls[4][1]["alerts"][0]
    assert alert["labels"] == {"alertname": "CheckoutApiErrorRate", "service": "checkout-api",
                               "signal": "error_rate", "severity": "sev1"}  # fmt: skip
    assert alert["annotations"]["health"] == "0.4"


def test_rejected_call_stops_the_run(repo, stub):
    handler, url = stub
    handler.status = 404  # PagerSage without the /ingest endpoints yet (task B10)
    with pytest.raises(RuntimeError, match="POST /ingest/deploy returned 404"):
        inject.run(inject.load_scenario("pool-exhaustion"), api=url, repo=repo, pause=False)
    assert len(handler.calls) == 1
