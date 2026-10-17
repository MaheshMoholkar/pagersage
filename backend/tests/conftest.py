import contextlib
import os
import uuid

os.environ["AGENTS_ENABLED"] = "false"  # never start real agents from API tests

import pytest
from redis.exceptions import RedisError

from pagersage import db


def _db_up() -> bool:
    try:
        return db.ping()
    except (RedisError, OSError):
        return False


@pytest.fixture(scope="session")
def falkordb_available() -> None:
    """Skip DB tests when FalkorDB is down locally; fail instead in CI (PAGERSAGE_REQUIRE_DB=1)."""
    if _db_up():
        return
    if os.environ.get("PAGERSAGE_REQUIRE_DB") == "1":
        pytest.fail("FalkorDB is not reachable and PAGERSAGE_REQUIRE_DB=1")
    pytest.skip("FalkorDB is not reachable; run `make db` first")


@pytest.fixture
def graph(falkordb_available):
    """A throwaway graph, deleted after the test. Never touches the real `pagersage` graph."""
    g = db.get_db().select_graph(f"test_{uuid.uuid4().hex[:12]}")
    yield g
    with contextlib.suppress(RedisError):  # the test may never have created it
        g.delete()


@pytest.fixture(scope="session")
def seeded_graph(falkordb_available):
    """Kestrel Pay seeded once per test run, for read-only tests. Never write to it."""
    from pagersage import seed

    g = db.get_db().select_graph(f"test_seeded_{uuid.uuid4().hex[:12]}")
    seed.seed_graph(g)
    yield g
    with contextlib.suppress(RedisError):
        g.delete()


@pytest.fixture
def tool_graph(seeded_graph, monkeypatch):
    """Point the agent tools (which call db.get_graph()) at the shared seeded graph."""
    monkeypatch.setattr(db, "get_graph", lambda name=None: seeded_graph)
    return seeded_graph


@pytest.fixture(scope="session")
def scenario_graph(falkordb_available):
    """Kestrel Pay seeded, then the pool-exhaustion scenario injected (tests/scenario.py): its
    changes, the live incident with its embedding, and both alerts' health through the real
    live-weight updater. Read-only."""
    from pagersage import embeddings, seed
    from pagersage.contracts import tools
    from tests import scenario

    g = db.get_db().select_graph(f"test_scenario_{uuid.uuid4().hex[:12]}")
    seed.seed_graph(g)
    g.query(scenario.SCENARIO, {"now": scenario.NOW})
    inc = scenario.LIVE_INCIDENT
    [vector] = embeddings.embed([embeddings.incident_text(inc["title"], inc["summary"])])
    g.query(
        "CREATE (:Incident {id:$id, title:$title, summary:$summary, status:'investigating', "
        "severity:'sev1', opened_at:$now, embedding:vecf32($v)})",
        {**inc, "now": scenario.NOW, "v": vector},
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(db, "get_graph", lambda name=None: g)
        for sid, health in scenario.HEALTH.items():
            tools.update_live_weights(sid, health)
    yield g
    with contextlib.suppress(RedisError):
        g.delete()


@pytest.fixture
def scenario(scenario_graph, monkeypatch):
    """Point the tools at the scenario graph, with the clock at the first alert."""
    from pagersage.contracts import tools
    from tests.scenario import NOW

    monkeypatch.setattr(db, "get_graph", lambda name=None: scenario_graph)
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    return scenario_graph


@pytest.fixture(scope="module")
def write_graph(falkordb_available):
    """Kestrel Pay seeded plus an open live incident INC-051, one per test module, for write
    tools. Tests in a module share it, so use distinct ids or count relative to before."""
    from pagersage import seed

    g = db.get_db().select_graph(f"test_write_{uuid.uuid4().hex[:12]}")
    seed.seed_graph(g)
    g.query(
        "CREATE (:Incident {id:'INC-051', title:'checkout-api errors', status:'investigating', "
        "severity:'sev1', opened_at:1792500000, summary:'payments-db pool exhausted'})"
    )
    yield g
    with contextlib.suppress(RedisError):
        g.delete()


@pytest.fixture
def writer(write_graph, monkeypatch):
    """Point the tools at this module's write_graph."""
    monkeypatch.setattr(db, "get_graph", lambda name=None: write_graph)
    return write_graph


@pytest.fixture
def api():
    """HTTP test client. Combine with tool_graph, scenario or writer to pick the graph the
    routes see (they call db.get_graph() per request)."""
    from fastapi.testclient import TestClient

    from pagersage.main import app

    with TestClient(app) as client:
        yield client
