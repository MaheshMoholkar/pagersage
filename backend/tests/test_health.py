from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from pagersage import db
from pagersage.main import app

client = TestClient(app)


def test_health_ok_when_falkordb_answers(falkordb_available):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "falkordb": "ok", "graph": "pagersage"}


def test_health_is_503_when_falkordb_is_down(monkeypatch):
    def down() -> bool:
        raise RedisConnectionError("connection refused")

    monkeypatch.setattr(db, "ping", down)
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["falkordb"] == "unreachable"


def test_cors_allows_the_frontend_origin():
    r = client.options(
        "/health",
        headers={"Origin": "http://localhost:3100", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3100"


def test_tool_errors_become_400s():
    from pagersage.contracts.tools import ToolError
    from pagersage.main import app

    def boom() -> None:
        raise ToolError("No service with id 'svc:nope'")

    app.add_api_route("/_test/tool-error", boom)
    try:
        r = client.get("/_test/tool-error")
    finally:
        app.router.routes[:] = [
            rt for rt in app.router.routes if getattr(rt, "path", None) != "/_test/tool-error"
        ]
    assert (r.status_code, r.json()) == (400, {"error": "No service with id 'svc:nope'"})
