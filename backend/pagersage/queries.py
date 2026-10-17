"""Named Cypher queries. Each agent tool runs queries from backend/queries/<name>.cypher.

One statement per file; parameters are always `$params`, never string-formatted.
See backend/queries/README.md.
"""

import re
from functools import cache
from pathlib import Path

QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"
_NAME = re.compile(r"[a-z][a-z0-9_]*")


@cache
def load(name: str) -> str:
    """Return the Cypher text of queries/<name>.cypher."""
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid query name {name!r}: use lowercase letters, digits, underscores")
    path = QUERIES_DIR / f"{name}.cypher"
    if not path.is_file():
        raise FileNotFoundError(f"No query named {name!r} in {QUERIES_DIR}")
    return path.read_text(encoding="utf-8")


def available() -> list[str]:
    """Names of every query file, sorted."""
    return sorted(p.stem for p in QUERIES_DIR.glob("*.cypher"))
