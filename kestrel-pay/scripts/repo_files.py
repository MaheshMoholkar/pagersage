"""Write services/<name>/README.md and CODEOWNERS from company/*.yaml (task K4), so the
Kestrel Pay repo looks like a real one. services/<name>/config.yaml is hand-written and never
touched here.

    cd backend && uv run python ../kestrel-pay/scripts/repo_files.py           # write
    cd backend && uv run python ../kestrel-pay/scripts/repo_files.py --check   # exit 1 if stale
"""

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPANY = ROOT / "company"
MARKER = "<!-- Generated from company/*.yaml by scripts/repo_files.py. Edit those, not this. -->"


def _load(name: str) -> dict:
    return yaml.safe_load((COMPANY / name).read_text(encoding="utf-8"))


def render() -> dict[Path, str]:
    """Every generated file, path -> content."""
    services = _load("topology.yaml")["services"]
    teams = _load("org.yaml")["teams"]
    runbooks = _load("runbooks.yaml")["runbooks"]
    owner = {svc: t for t in teams for svc in t["owns"]}
    callers: dict[str, list[str]] = {}
    for s in services:
        for d in s.get("depends_on", []):
            callers.setdefault(d["to"], []).append(s["name"])

    out: dict[Path, str] = {}
    for s in services:
        name, team = s["name"], owner[s["name"]]
        lines = [
            f"# {name}",
            "",
            s["description"],
            "",
            "| | |",
            "|---|---|",
            f"| Tier | {s['tier']} |",
            f"| Language | {s['language']} |",
            f"| Owner | {team['name']} (`{team['slack_channel']}`) |",
            "| Config | [`config.yaml`](config.yaml) |",
        ]
        if deps := s.get("depends_on"):
            lines += ["", "## Depends on", ""]
            lines += [
                f"- [{d['to']}](../{d['to']}/): {d['calls_per_min']} calls/min, "
                f"p99 {d['p99_ms']} ms"
                for d in deps
            ]
        if up := sorted(callers.get(name, [])):
            lines += ["", "## Called by", ""] + [f"- [{c}](../{c}/)" for c in up]
        if rbs := [rb for rb in runbooks if rb["service"] == name]:
            lines += ["", "## Runbooks", ""] + [f"- {rb['title']} (`{rb['slug']}`)" for rb in rbs]
        out[ROOT / "services" / name / "README.md"] = "\n".join([*lines, "", MARKER, ""])

    width = max(len(s["name"]) for s in services) + len("/services//")
    codeowners = [
        "# Generated from company/org.yaml by scripts/repo_files.py. Edit that, not this.",
        f"{'/company/':<{width}} @kestrel-pay/platform",
    ]
    codeowners += [
        f"{f'/services/{s["name"]}/':<{width}} @kestrel-pay/{owner[s['name']]['slug']}"
        for s in services
    ]
    out[ROOT / "CODEOWNERS"] = "\n".join([*codeowners, ""])
    return out


def stale() -> list[Path]:
    """Generated files whose content on disk differs from render()."""
    return [
        p
        for p, text in render().items()
        if not p.is_file() or p.read_text(encoding="utf-8") != text
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if generated files are stale")
    args = ap.parse_args(argv)
    if args.check:
        bad = stale()
        for p in bad:
            print(f"stale: {p.relative_to(ROOT)}", file=sys.stderr)
        return 1 if bad else 0
    for p, text in render().items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    print(f"wrote {len(render())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
