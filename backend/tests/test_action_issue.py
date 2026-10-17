"""open_issue (B08): a GitHub issue with the root-cause path and suspect commit."""

import httpx
import pytest

from pagersage.config import get_settings
from pagersage.contracts import tools
from pagersage.contracts.events import EventKind, Highlight
from pagersage.contracts.tools import ToolError
from tests.test_action_page import incident  # noqa: F401 (fixture)

SHA = "1a132292cfe942b80c1846e1bcf9769685f18a79"
URL = "https://github.com/owner/pagersage-demo/issues/7"


class GitHub:
    def __init__(self, status=201, error=None):
        self.calls, self.status, self.error = [], status, error

    def __call__(self, url, json, headers, timeout):
        self.calls.append((url, json, headers))
        if self.error:
            raise self.error
        return httpx.Response(self.status, json={"html_url": URL})


@pytest.fixture
def github(monkeypatch):
    monkeypatch.setattr(get_settings(), "github_token", "ghp_test")
    monkeypatch.setattr(get_settings(), "github_issues_repo", "owner/pagersage-demo")
    gh = GitHub()
    monkeypatch.setattr(tools, "_post", gh)
    return gh


def _found_root_cause(iid):
    tools.append_event(
        iid,
        EventKind.FINDING,
        "pool cut",
        highlight=Highlight(
            nodes=[
                "svc:checkout-api",
                "svc:payments-svc",
                "svc:payments-db",
                "dep-0416",
                SHA,
                "person:tomas",
            ],
            edges=[("svc:checkout-api", "DEPENDS_ON", "svc:payments-svc")],
        ),
    )


def test_issue_carries_the_root_cause_path_and_commit(writer, incident, github):  # noqa: F811
    _found_root_cause(incident)

    r = tools.open_issue(incident, "payments-db pool exhausted", "Raise the pool, then fix.")

    assert (r.ok, r.url, r.action) == (True, URL, "issue")
    [(url, body, headers)] = github.calls
    assert url == "https://api.github.com/repos/owner/pagersage-demo/issues"
    assert headers["Authorization"] == "Bearer ghp_test"
    assert body["title"] == f"[{incident}] payments-db pool exhausted"
    text = body["body"]
    assert text.startswith("Raise the pool, then fix.")
    assert "checkout-api → payments-svc → payments-db" in text
    assert "dep-0416" in text and SHA[:7] in text and incident in text
    [[data]] = writer.ro_query(
        "MATCH (e:Event {kind:'action'})-[:PART_OF]->(:Incident {id:$iid}) RETURN e.data",
        {"iid": incident},
    ).result_set
    assert URL in data


def test_without_credentials_nothing_is_opened(writer, incident, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "github_token", None)

    r = tools.open_issue(incident, "t", "b")

    assert r.ok is False and "GITHUB_TOKEN" in r.detail


@pytest.mark.parametrize("gh", [GitHub(status=422), GitHub(error=httpx.ReadTimeout("slow"))])
def test_github_failures_are_reported_not_raised(writer, incident, github, monkeypatch, gh):  # noqa: F811
    monkeypatch.setattr(tools, "_post", gh)

    r = tools.open_issue(incident, "t", "b")

    assert r.ok is False and r.url is None


def test_unknown_incident_is_a_tool_error(writer, github):
    with pytest.raises(ToolError):
        tools.open_issue("INC-999", "t", "b")
    assert github.calls == []
