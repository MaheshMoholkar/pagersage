"""T1 find_service (G06): free text to service ids, typo- and prefix-tolerant, names first."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError


def _ids(q, limit=3):
    return [m.id for m in tools.find_service(q, limit)]


def test_typo_finds_payments_services(tool_graph):
    assert _ids("paymnts", 2) == ["svc:payments-db", "svc:payments-svc"]


def test_prefix_finds_payments_svc(tool_graph):
    assert "svc:payments-svc" in _ids("pay*")


@pytest.mark.parametrize(
    ("q", "first"),
    [
        ("payments-db", "svc:payments-db"),  # the hyphen is not RediSearch's NOT
        ("payments db", "svc:payments-db"),
        ("the payments database", "svc:payments-db"),
        ("kafak", "svc:kafka"),
        ("checkout api", "svc:checkout-api"),
        ("Ledger SVC", "svc:ledger-svc"),
    ],
)
def test_best_match_comes_first(tool_graph, q, first):
    assert _ids(q)[0] == first


def test_falls_back_to_descriptions(tool_graph):
    # No service is named postgres; the databases say so in their description.
    assert set(_ids("postgres", 10)) >= {"svc:payments-db", "svc:ledger-db"}


def test_name_matches_rank_above_description_matches(tool_graph):
    # reconciliation-job's description says "payments" a lot; the payments services win anyway.
    assert _ids("payments", 2) == ["svc:payments-db", "svc:payments-svc"]


def test_results_are_unique_and_limited(tool_graph):
    matches = tools.find_service("svc", 5)

    assert len(matches) == 5
    assert len({m.id for m in matches}) == 5
    assert all(m.name and m.score > 0 for m in matches)


def test_no_match_is_an_empty_list(tool_graph):
    assert tools.find_service("zzqxv") == []


@pytest.mark.parametrize(("q", "limit"), [("", 3), ("  !! ", 3), ("payments", 0), ("pay*(", 3)])
def test_bad_input_is_a_tool_error(tool_graph, q, limit):
    with pytest.raises(ToolError):
        tools.find_service(q, limit)
