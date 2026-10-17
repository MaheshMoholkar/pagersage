"""T8 check_policy (A10): Kestrel Pay's policies (kestrel-pay/company/policies.yaml) by action
and service tier."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.schema import ActionKind
from pagersage.contracts.tools import ToolError


def _ids(action, sid):
    return [p.id for p in tools.check_policy(action, sid)]


def test_rolling_back_a_tier1_database_hits_both_rollback_policies(tool_graph):
    hits = tools.check_policy(ActionKind.ROLLBACK, "svc:payments-db")

    assert [p.id for p in hits] == ["pol:no-database-rollback", "pol:tier1-rollback-ack"]
    assert hits[1].name == "Tier-1 rollback requires owner ack"
    assert "wait for an ack" in hits[1].rule


def test_max_tier_limits_where_a_policy_applies(tool_graph):
    assert _ids("rollback", "svc:inventory-svc") == ["pol:no-database-rollback"]  # tier 2
    assert _ids("issue", "svc:pricing-svc") == ["pol:issue-cites-root-cause"]  # tier 2
    assert _ids("issue", "svc:search-api") == []  # tier 3: no issue policy


def test_paging_always_goes_to_the_on_call_first(tool_graph):
    assert _ids(ActionKind.PAGE, "svc:search-api") == ["pol:page-on-call-first"]


@pytest.mark.parametrize(("action", "sid"), [("rollback", "svc:nope"), ("reboot", "svc:edge")])
def test_bad_input_is_a_tool_error(tool_graph, action, sid):
    with pytest.raises(ToolError):
        tools.check_policy(action, sid)
