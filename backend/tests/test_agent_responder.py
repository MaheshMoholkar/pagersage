"""Responder (A07): pages the on-call, opens the issue and rolls back only inside policy, then
records a decision with APPLIED_POLICY and hands off to the Scribe."""

import itertools

import httpx
import pytest

from pagersage.agents import orchestrator
from pagersage.config import get_settings
from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from tests.fake_claude import FakeClaude, reply, use

RESP = AgentName.RESPONDER
_ids = itertools.count(20)


class Post:
    """Stands in for httpx.post: Discord answers 204, GitHub 201 with the issue URL."""

    def __init__(self):
        self.urls = []

    def __call__(self, url, json, timeout, headers=None):
        self.urls.append(url)
        if "discord" in url:
            return httpx.Response(204)
        return httpx.Response(201, json={"html_url": "https://github.com/acme/demo/issues/7"})


@pytest.fixture
def post(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_webhook_url", "https://discord.example/hook")
    monkeypatch.setattr(settings, "github_token", "ghp_test")
    monkeypatch.setattr(settings, "github_issues_repo", "acme/demo")
    sent = Post()
    monkeypatch.setattr(tools, "_post", sent)
    return sent


@pytest.fixture
def incident(writer):
    iid = f"INC-1{next(_ids):02d}"
    writer.query(
        "MATCH (s:Service {id:'svc:payments-db'}) "
        "CREATE (i:Incident {id:$id, title:'checkout-api errors: pool exhausted', "
        "severity:'sev1', status:'investigating', opened_at:1792500000, summary:''}), "
        "(a:Alert {id:$aid, ts:1792500000, signal:'saturation', value:0.97, threshold:0.9, "
        "severity:'sev1'})-[:PART_OF]->(i), (a)-[:FIRED_ON]->(s)",
        {"id": iid, "aid": f"alt-7{iid[-3:]}"},
    )
    return iid


def _check(action, sid="svc:payments-db"):
    return use("check_policy", action=action, service_id=sid)


def _decision(policies, evidence):
    return use(
        "record_decision",
        what="Paged priya and opened an issue; no rollback",
        why="cfg-0061 is a config change on a database: the runbook fixes it",
        confidence=0.9,
        evidence_ids=evidence,
        policy_ids=policies,
    )


def _actions(g, iid):
    return g.ro_query(
        "MATCH (e:Event {incident_id:$i, kind:'action'}) RETURN e.text ORDER BY e.seq",
        {"i": iid},
    ).result_set


def test_responder_pages_opens_the_issue_and_applies_policy(writer, incident, post):
    policies = ["pol:issue-cites-root-cause", "pol:no-database-rollback", "pol:page-on-call-first"]
    api = FakeClaude(
        [
            reply(use("who_to_page", service_id="svc:payments-db")),
            reply(_check("page"), _check("issue"), _check("rollback")),
            reply(
                use("page_owner", handle="priya", message="cfg-0061 cut the pool; raise it"),
                use("open_issue", title="payments-db pool cut by cfg-0061", body="Path ..."),
            ),
            reply(_decision(policies, ["svc:payments-db", "person:priya"])),
            reply(use("handoff", note="Paged priya; issue #7", state_patch_json="{}")),
        ]
    )

    assert orchestrator.run_agent(RESP, incident, api=api).ok

    assert [u.split("/")[2] for u in post.urls] == ["discord.example", "api.github.com"]
    assert _actions(writer, incident) == [["Paged priya on Discord"], ["Opened a GitHub issue"]]
    [[applied, scribe]] = writer.ro_query(
        "MATCH (d:Decision)-[:ABOUT]->(i:Incident {id:$i}), (d)-[:APPLIED_POLICY]->(p:Policy) "
        "MATCH (i)-[:ASSIGNED_TO]->(a:Agent) RETURN collect(p.id), a.name",
        {"i": incident},
    ).result_set
    assert sorted(applied) == policies and scribe == "scribe"


def test_responder_cannot_act_before_checking_policy(writer, incident, post):
    api = FakeClaude(
        [
            reply(use("page_owner", handle="priya", message="pool")),
            reply(_check("page")),
            reply(use("page_owner", handle="priya", message="pool")),
            reply(use("handoff", note="Paged priya", state_patch_json="{}")),
        ]
    )

    assert orchestrator.run_agent(RESP, incident, api=api).ok

    assert len(post.urls) == 1
    refused = api.requests[1]["messages"][-1]["content"][0]
    assert refused["is_error"] and refused["content"].startswith("Refused")


def test_responder_rolls_back_a_deploy_policy_allows(writer, incident, post):
    [[deploy]] = writer.ro_query(
        "MATCH (d:Deploy)-[:TARGETED]->(:Service {id:'svc:inventory-svc'}) "
        "WHERE d.status = 'ok' RETURN d.id ORDER BY d.ts DESC LIMIT 1"
    ).result_set
    api = FakeClaude(
        [
            reply(_check("rollback", "svc:inventory-svc")),
            reply(use("rollback", service_id="svc:inventory-svc", deploy_id=deploy)),
            reply(use("handoff", note=f"Rolled back {deploy}", state_patch_json="{}")),
        ]
    )

    assert orchestrator.run_agent(RESP, incident, api=api).ok

    [[text]] = _actions(writer, incident)
    assert text.startswith("Simulated rollback: inventory-svc back to") and deploy in text
