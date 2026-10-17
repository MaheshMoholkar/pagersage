"""Kestrel Pay's own tests. They run under the backend's environment (`make test` collects
this folder) but never import pagersage: Kestrel Pay is a separate project."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(rel: str) -> ModuleType:
    """Import one of Kestrel Pay's scripts by path (they are standalone files, not a package)."""
    path = ROOT / rel
    name = f"kestrel_{path.stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
