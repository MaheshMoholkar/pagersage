"""T5 who_to_page (G11): the owning team's on-call now, then the two most recent authors."""

from datetime import UTC, datetime

import pytest

from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError


def _ts(day: int) -> int:
    return int(datetime(2026, 10, day, 12, tzinfo=UTC).timestamp())


def _page(sid, now):
    return [(t.handle, t.team, t.reason) for t in tools.who_to_page(sid, now)]


def test_payments_db_during_the_demo_week(tool_graph):
    # priya is on call Oct 12-18; kwame and priya shipped the latest payments-db deploy, then
    # hana and tomas (tie broken by handle). priya is not listed twice.
    assert _page("svc:payments-db", _ts(16)) == [
        ("priya", "Payments", "on_call"),
        ("kwame", "Payments", "recent_author"),
        ("hana", "Payments", "recent_author"),
    ]


def test_on_call_follows_the_rotation(tool_graph):
    assert _page("svc:payments-db", _ts(20))[0] == ("tomas", "Payments", "on_call")


def test_sole_author_on_ledger_svc(tool_graph):
    # Planted pattern: ines is ledger-svc's only recent author; raj has the first ledger shift.
    assert _page("svc:ledger-svc", _ts(16)) == [
        ("raj", "Ledger", "on_call"),
        ("ines", "Ledger", "recent_author"),
    ]


def test_outside_any_rotation_only_authors_are_paged(tool_graph):
    targets = tools.who_to_page("svc:payments-db", _ts(2) + 400 * 86400)

    assert [t.reason for t in targets] == ["recent_author", "recent_author"]


def test_deploys_after_now_do_not_count(tool_graph):
    before_history = _ts(1) - 200 * 86400
    assert tools.who_to_page("svc:payments-db", before_history) == []


def test_now_defaults_to_the_clock(tool_graph, monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: _ts(16))
    assert tools.who_to_page("svc:payments-db")[0].handle == "priya"


def test_unknown_service_is_a_tool_error(tool_graph):
    with pytest.raises(ToolError):
        tools.who_to_page("svc:nope", _ts(16))
