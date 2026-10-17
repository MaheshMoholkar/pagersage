"""docs/cypher.md (G19) is generated from backend/queries/; keep it current and complete."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cypher_catalogue.py"


@pytest.fixture(scope="module")
def catalogue():
    spec = importlib.util.spec_from_file_location("cypher_catalogue", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docs_cypher_md_is_up_to_date(catalogue):
    assert catalogue.OUT.read_text(encoding="utf-8") == catalogue.render(), (
        "docs/cypher.md is stale: run `make catalogue` and commit it"
    )


def test_every_query_is_explained_and_run_by_code(catalogue):
    files = sorted(catalogue.QUERIES.glob("*.cypher"))
    used = catalogue.callers({f.stem for f in files})
    for f in files:
        assert catalogue.summary(f.read_text(encoding="utf-8")), f"{f.name} needs a // header"
        assert used.get(f.stem), f"{f.name} is not run by any function in pagersage/"


def test_every_query_lands_in_exactly_one_section(catalogue):
    text = catalogue.render()
    for f in catalogue.QUERIES.glob("*.cypher"):
        assert text.count(f"[`{f.stem}`]") == 1, f.stem
