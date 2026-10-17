"""T4 root_cause_path (G10): the weighted shortest path from the alerting service to the
suspect, with the change, commits and people behind it, ready for the canvas to highlight."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError


def test_pool_cut_path_runs_through_payments_svc(scenario):
    p = tools.root_cause_path("svc:checkout-api", "svc:payments-db", "cfg-0061")

    assert p.services == ["svc:checkout-api", "svc:payments-svc", "svc:payments-db"]
    # healthy edge into payments-svc (100) + sick payments-db (live weight 15)
    assert p.path_weight == 115
    assert (p.change_id, p.commits, p.authors) == ("cfg-0061", [], ["tomas"])


def test_deploy_brings_its_commits_and_authors(scenario):
    p = tools.root_cause_path("svc:checkout-api", "svc:payments-svc", "dep-0416")

    assert p.services == ["svc:checkout-api", "svc:payments-svc"]
    assert (p.commits, p.authors) == (["aaaa111"], ["tomas"])


def test_highlight_lights_the_path_change_commits_and_people(scenario):
    p = tools.root_cause_path("svc:checkout-api", "svc:payments-svc", "dep-0416")

    assert p.highlight.nodes == [
        "svc:checkout-api",
        "svc:payments-svc",
        "dep-0416",
        "aaaa111",
        "person:tomas",
    ]
    assert p.highlight.edges == [
        ("svc:checkout-api", "DEPENDS_ON", "svc:payments-svc"),
        ("dep-0416", "TARGETED", "svc:payments-svc"),
        ("dep-0416", "CONTAINS", "aaaa111"),
        ("person:tomas", "AUTHORED", "aaaa111"),
    ]


def test_config_change_highlight_uses_changed_and_made(scenario):
    p = tools.root_cause_path("svc:checkout-api", "svc:payments-db", "cfg-0061")

    assert p.highlight.edges[-2:] == [
        ("cfg-0061", "CHANGED", "svc:payments-db"),
        ("person:tomas", "MADE", "cfg-0061"),
    ]


def test_a_change_on_the_alerting_service_is_a_zero_hop_path(scenario):
    p = tools.root_cause_path("svc:checkout-api", "svc:checkout-api", "dep-0417")

    assert (p.services, p.path_weight, p.authors) == (["svc:checkout-api"], 0, ["ben"])


@pytest.mark.parametrize(
    ("alerting", "suspect", "change"),
    [
        ("svc:nope", "svc:payments-db", "cfg-0061"),  # unknown service
        ("svc:checkout-api", "svc:payments-db", "cfg-9999"),  # unknown change
        ("svc:checkout-api", "svc:payments-svc", "cfg-0061"),  # change is on another service
        ("svc:payments-db", "svc:checkout-api", "dep-0417"),  # suspect is upstream, no path
    ],
)
def test_bad_input_is_a_tool_error(scenario, alerting, suspect, change):
    with pytest.raises(ToolError):
        tools.root_cause_path(alerting, suspect, change)
