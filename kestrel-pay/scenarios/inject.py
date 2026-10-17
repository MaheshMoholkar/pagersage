"""Break Kestrel Pay and tell PagerSage about it, the way a CD system and Alertmanager would
(tasks K7, K8). PagerSage is only reached over HTTP; FalkorDB is never touched.

    make inject SCENARIO=pool-exhaustion
    cd backend && uv run python ../kestrel-pay/scenarios/inject.py pool-exhaustion [--dry-run]

A scenario (scenarios/<name>.yaml) is a list of steps, run in order:
  commit         a real git commit on a fresh branch incident/<name>-<utc time>, made with git
                 plumbing so the working tree and current branch are untouched
  deploy         POST /ingest/deploy with the commits it ships
  config_change  POST /ingest/config-change (old value read from the service's config.yaml)
  alert          POST /alerts, Alertmanager webhook format
`at` is seconds relative to the first alert (now); ids continue from history/export/, so
run PagerSage's `make reset` before injecting again.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"
EXPORT = ROOT / "history" / "export"
EMAIL_DOMAIN = "kestrelpay.example"
STEP_KINDS = ("commit", "deploy", "config_change", "alert")
SIGNALS = ("error_rate", "latency_p99", "saturation")
SEVERITIES = ("sev1", "sev2", "sev3")


# ── scenario files ────────────────────────────────────────────────────────


@dataclass
class Step:
    kind: str
    name: str
    spec: dict[str, Any]

    @property
    def at(self) -> int:
        return int(self.spec.get("at", 0))


@dataclass
class Scenario:
    name: str
    summary: str
    expect: dict[str, Any]
    steps: list[Step] = field(default_factory=list)

    def step(self, name: str) -> Step:
        return next(s for s in self.steps if s.name == name)


def _company() -> tuple[set[str], dict[str, dict], set[str]]:
    load = lambda n: yaml.safe_load((ROOT / "company" / n).read_text(encoding="utf-8"))  # noqa: E731
    services = {s["name"] for s in load("topology.yaml")["services"]}
    people = {p["handle"]: p for p in load("org.yaml")["people"]}
    runbooks = {rb["slug"] for rb in load("runbooks.yaml")["runbooks"]}
    return services, people, runbooks


def load_scenario(name: str) -> Scenario:
    """Read and check a scenario. Raises ValueError naming the first problem."""
    path = SCENARIOS / f"{name}.yaml"
    if not path.is_file():
        known = sorted(p.stem for p in SCENARIOS.glob("*.yaml"))
        raise ValueError(f"No scenario {name!r}; known: {known}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    services, people, runbooks = _company()
    sc = Scenario(raw["name"], raw["summary"].strip(), raw.get("expect", {}))
    seen: dict[str, str] = {}

    def need(ok: bool, what: str) -> None:
        if not ok:
            raise ValueError(f"{name}: {what}")

    for item in raw["steps"]:
        kinds = [k for k in STEP_KINDS if k in item]
        need(len(kinds) == 1, f"step {item} needs exactly one of {STEP_KINDS}")
        kind, step_name = kinds[0], item[kinds[0]]
        need(step_name not in seen, f"duplicate step name {step_name!r}")
        spec = {k: v for k, v in item.items() if k != kind}
        if kind == "commit":
            need(spec.get("author") in people, f"{step_name}: unknown author")
            need(("set" in spec) != ("append" in spec), f"{step_name}: needs `set` or `append`")
            parts = Path(spec.get("file", "")).parts
            need(len(parts) > 2 and parts[0] == "services" and parts[1] in services,
                 f"{step_name}: file must be under services/<service>/")  # fmt: skip
        elif kind == "deploy":
            need(spec.get("service") in services, f"{step_name}: unknown service")
            need(spec.get("deployed_by") in people, f"{step_name}: unknown deployer")
            for c in spec.get("commits", []):
                need(seen.get(c) == "commit", f"{step_name}: {c!r} is not an earlier commit step")
        elif kind == "config_change":
            need(spec.get("service") in services, f"{step_name}: unknown service")
            need(spec.get("made_by") in people, f"{step_name}: unknown person")
            need(spec.get("key") in _config(ROOT, spec["service"]), f"{step_name}: unknown key")
        elif kind == "alert":
            need(spec.get("service") in services, f"{step_name}: unknown service")
            need(spec.get("signal") in SIGNALS, f"{step_name}: bad signal")
            need(spec.get("severity") in SEVERITIES, f"{step_name}: bad severity")
            need(0 <= float(spec.get("health", 1)) <= 1, f"{step_name}: health must be 0-1")
        seen[step_name] = kind
        sc.steps.append(Step(kind, step_name, spec))

    alerts = [s for s in sc.steps if s.kind == "alert"]
    need(bool(alerts) and alerts[0].at == 0, "the first alert is `at: 0` (now)")
    e = sc.expect
    for key in ("alerting_service", "root_service"):
        need(e.get(key) in services, f"expect.{key} is not a service")
    need(seen.get(e.get("cause")) in ("deploy", "config_change"), "expect.cause must name a change")
    decoy = e.get("decoy")
    need(decoy is None or seen.get(decoy) == "deploy", "expect.decoy must be a deploy")
    need(all(s in services for s in e.get("path", [])), "expect.path has unknown services")
    need(e.get("runbook") in runbooks, "expect.runbook is not a runbook")
    past = {i["id"] for i in _export("incidents")}
    need(all(i in past for i in e.get("similar", [])), "expect.similar names unknown incidents")
    return sc


def _config(base: Path, service: str) -> dict[str, Any]:
    return yaml.safe_load((base / "services" / service / "config.yaml").read_text(encoding="utf-8"))


def fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ── ids that continue Kestrel Pay's own history ───────────────────────────


def _export(name: str) -> list[dict]:
    lines = (EXPORT / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class Ids:
    def __init__(self) -> None:
        deploys = _export("deploys")
        self.deploy = max(int(d["id"][4:]) for d in deploys)
        self.config = max(int(c["id"][4:]) for c in _export("config_changes"))
        self.versions = {d["service"]: d["version"] for d in deploys}  # export is in time order

    def next_deploy(self) -> str:
        self.deploy += 1
        return f"dep-{self.deploy:04d}"

    def next_config(self) -> str:
        self.config += 1
        return f"cfg-{self.config:04d}"

    def next_version(self, service: str) -> str:
        major, minor, patch = (int(x) for x in self.versions.get(service, "v1.0.0")[1:].split("."))
        self.versions[service] = f"v{major}.{minor}.{patch + 1}"
        return self.versions[service]


# ── git ───────────────────────────────────────────────────────────────────


class Git:
    """Commits on a new branch without checking it out: blob -> temp index -> tree -> commit."""

    def __init__(self, repo: Path, prefix: str) -> None:
        self.repo, self.prefix = repo, prefix
        self.head = self.run("rev-parse", "HEAD")

    def run(self, *args: str, stdin: str | None = None, env: dict | None = None) -> str:
        out = subprocess.run(
            ["git", *args],
            cwd=self.repo,
            input=stdin,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
            check=True,
        )
        return out.stdout.strip()

    def path(self, file: str) -> str:
        return f"{self.prefix}/{file}" if self.prefix else file

    def show(self, rev: str, file: str) -> str | None:
        try:
            return self.run("show", f"{rev}:{self.path(file)}")
        except subprocess.CalledProcessError:
            return None

    def commit(self, parent: str, file: str, content: str, message: str, who: dict, ts: int) -> str:
        blob = self.run("hash-object", "-w", "--stdin", stdin=content)
        with tempfile.TemporaryDirectory() as tmp:
            index = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
            self.run("read-tree", parent, env=index)
            self.run("update-index", "--add", "--cacheinfo", f"100644,{blob},{self.path(file)}",
                     env=index)  # fmt: skip
            tree = self.run("write-tree", env=index)
        stamp = f"@{ts} +0000"
        ident = {
            "GIT_AUTHOR_NAME": who["name"],
            "GIT_AUTHOR_EMAIL": f"{who['handle']}@{EMAIL_DOMAIN}",
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_NAME": who["name"],
            "GIT_COMMITTER_EMAIL": f"{who['handle']}@{EMAIL_DOMAIN}",
            "GIT_COMMITTER_DATE": stamp,
        }
        return self.run("commit-tree", tree, "-p", parent, "-m", message, env=ident)


def _edit(text: str, changes: dict[str, Any], file: str) -> str:
    """Set top-level YAML keys in place, keeping comments and order."""
    for key, value in changes.items():
        line = f"{key}: {yaml.safe_dump(value, default_flow_style=True).strip()}"
        line = line.removesuffix(" ...")  # safe_dump ends bare scalars with a document marker
        text, n = re.subn(rf"(?m)^{re.escape(key)}:.*$", line, text)
        if n != 1:
            raise ValueError(f"{file}: expected one `{key}:` line, found {n}")
    return text if text.endswith("\n") else text + "\n"


# ── HTTP ──────────────────────────────────────────────────────────────────


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def alertmanager_payload(spec: dict[str, Any], ts: int) -> dict[str, Any]:
    """One firing alert as an Alertmanager webhook (version 4) would deliver it."""
    words = re.split(r"[-_]", f"{spec['service']}_{spec['signal']}")
    alertname = "".join(w.capitalize() for w in words)
    labels = {
        "alertname": alertname,
        "service": spec["service"],
        "signal": spec["signal"],
        "severity": spec["severity"],
    }
    annotations = {
        "value": fmt(spec["value"]),
        "threshold": fmt(spec["threshold"]),
        "health": fmt(spec["health"]),
        "summary": f"{spec['service']} {spec['signal']} {spec['value']} > {spec['threshold']}",
    }
    fingerprint = hashlib.sha1(json.dumps(labels, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "version": "4",
        "groupKey": f'{{}}:{{alertname="{alertname}"}}',
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "pagersage",
        "groupLabels": {"alertname": alertname},
        "commonLabels": labels,
        "commonAnnotations": annotations,
        "externalURL": f"http://alertmanager.{EMAIL_DOMAIN}",
        "alerts": [
            {
                "status": "firing",
                "labels": labels,
                "annotations": annotations,
                "startsAt": _iso(ts),
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": f"http://prometheus.{EMAIL_DOMAIN}/graph?g0.expr={alertname}",
                "fingerprint": fingerprint,
            }
        ],
    }


def post(api: str, path: str, body: dict[str, Any]) -> int:
    req = urllib.request.Request(
        f"{api.rstrip('/')}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


# ── running a scenario ────────────────────────────────────────────────────


def run(
    sc: Scenario,
    *,
    api: str,
    repo: Path | None,
    dry_run: bool = False,
    pause: bool = True,
    push: bool = False,
    now: int | None = None,
) -> dict[str, str]:
    """Run every step; returns step name -> id or sha. Raises RuntimeError if PagerSage
    rejects a call (or is down), after the remaining calls were skipped."""
    t0 = now if now is not None else int(time.time())
    _, people, _ = _company()
    ids = Ids()
    made: dict[str, str] = {}
    commits: dict[str, dict] = {}
    git = None if dry_run else _git(repo)
    parent = git.head if git else None
    branch = f"incident/{sc.name}-{datetime.fromtimestamp(t0, UTC):%Y%m%d-%H%M%S}"

    def send(path: str, body: dict) -> None:
        if dry_run:
            print(f"  POST {path} {json.dumps(body)}")
            return
        try:
            status = post(api, path, body)
        except OSError as exc:
            raise RuntimeError(f"PagerSage unreachable at {api}: {exc}") from exc
        if not 200 <= status < 300:
            raise RuntimeError(f"POST {path} returned {status}")

    for step in sc.steps:
        s, ts = step.spec, t0 + step.at
        if pause and not dry_run and s.get("pause"):
            time.sleep(float(s["pause"]))
        if step.kind == "commit":
            ts = t0 + int(s.get("at", -600))
            who = people[s["author"]]
            if git:
                before = git.show(parent, s["file"])
                if "set" in s:
                    if before is None:
                        raise ValueError(f"{s['file']} does not exist at {parent[:7]}")
                    after = _edit(before, s["set"], s["file"])
                else:
                    after = (before or "") + s["append"]
                parent = git.commit(parent, s["file"], after, s["message"], who, ts)
                git.run("update-ref", f"refs/heads/{branch}", parent)
                sha = parent
            else:
                sha = hashlib.sha1(f"dry-run:{step.name}".encode()).hexdigest()
            commits[step.name] = {"sha": sha, "message": s["message"], "author": s["author"],
                                  "ts": ts}  # fmt: skip
            made[step.name] = sha
            print(f"commit {sha[:7]} {s['file']}: {s['message']}")
        elif step.kind == "deploy":
            body = {
                "id": ids.next_deploy(),
                "service": s["service"],
                "version": ids.next_version(s["service"]),
                "ts": ts,
                "deployed_by": s["deployed_by"],
                "commits": [commits[c] for c in s.get("commits", [])],
            }
            made[step.name] = body["id"]
            print(f"deploy {body['id']} {s['service']} {body['version']} by {s['deployed_by']}")
            send("/ingest/deploy", body)
        elif step.kind == "config_change":
            config_file = f"services/{s['service']}/config.yaml"
            base = git.show(git.head, config_file) if git else None
            current = yaml.safe_load(base) if base else _config(ROOT, s["service"])
            old = current[s["key"]]
            body = {
                "id": ids.next_config(),
                "service": s["service"],
                "key": s["key"],
                "old": fmt(old),
                "new": fmt(s["to"]),
                "ts": ts,
                "made_by": s["made_by"],
            }
            made[step.name] = body["id"]
            print(f"config {body['id']} {s['service']}.{s['key']}: {body['old']} -> {body['new']}")
            send("/ingest/config-change", body)
        else:
            print(f"alert {s['service']} {s['signal']}={s['value']} health={s['health']}")
            send("/alerts", alertmanager_payload(s, ts))

    if git and commits:
        print(f"branch {branch} -> {parent[:7]} (working tree untouched)")
        if push:
            git.run("push", "origin", branch)
            print(f"pushed {branch} to origin")
    return made


def _git(repo: Path | None) -> Git:
    """Git for `repo` (default: the repo Kestrel Pay lives in); Kestrel paths are prefixed
    with Kestrel Pay's folder inside that repo."""
    top = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True
    ).strip())  # fmt: skip
    prefix = ROOT.relative_to(top).as_posix()
    return Git(repo or top, "" if prefix == "." else prefix)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a Kestrel Pay incident scenario.")
    ap.add_argument("scenario", help="scenario name, e.g. pool-exhaustion")
    ap.add_argument("--api", default=os.environ.get("PAGERSAGE_API_URL", "http://localhost:8000"))
    ap.add_argument("--dry-run", action="store_true", help="print the calls; no git, no HTTP")
    ap.add_argument("--no-pause", action="store_true", help="skip the pauses between alerts")
    ap.add_argument("--push", action="store_true", help="push the incident branch to origin")
    ap.add_argument("--repo", type=Path, help=argparse.SUPPRESS)  # tests use a scratch repo
    args = ap.parse_args(argv)
    try:
        sc = load_scenario(args.scenario)
        print(f"{sc.name}: {sc.summary}")
        run(sc, api=args.api, repo=args.repo, dry_run=args.dry_run, pause=not args.no_pause,
            push=args.push)  # fmt: skip
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"inject: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
