"""page_owner (B07): page the on-call on Discord, and log the action on the timeline."""

import httpx
import pytest

from pagersage.config import get_settings
from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError
from tests.test_api_alerts import payload

HOOK = "https://discord.example/api/webhooks/1/abc"


class Sent:
    def __init__(self, status=204, error=None):
        self.calls, self.status, self.error = [], status, error

    def __call__(self, url, json, timeout):
        self.calls.append((url, json))
        if self.error:
            raise self.error
        return httpx.Response(self.status)


@pytest.fixture
def incident(api, writer, monkeypatch):
    from pagersage import runtime

    monkeypatch.setattr(runtime, "_opened", [])
    t0 = 1_792_900_000 + len(writer.ro_query("MATCH (i:Incident) RETURN i").result_set) * 3600
    return api.post("/alerts", json=payload("payments-db", ts=t0)).json()["incidents"][0][
        "incident_id"
    ]


@pytest.fixture
def discord(monkeypatch):
    monkeypatch.setattr(get_settings(), "discord_webhook_url", HOOK)
    sent = Sent()
    monkeypatch.setattr(tools, "_post", sent)
    return sent


def _last_event(g, iid):
    return g.ro_query(
        "MATCH (e:Event)-[:PART_OF]->(:Incident {id:$iid}) RETURN e.kind, e.text, e.data "
        "ORDER BY e.seq DESC LIMIT 1",
        {"iid": iid},
    ).result_set[0]


def test_page_posts_incident_service_and_handle_to_discord(writer, incident, discord):
    r = tools.page_owner(incident, "priya", "Suspect: cfg-0061 cut payments-db max_pool_size.")

    assert (r.ok, r.action) == (True, "page")
    [(url, body)] = discord.calls
    assert url == HOOK and body["username"] == "PagerSage"
    text = body["content"]
    for part in (incident, "payments-db", "@priya", "Priya", "cfg-0061", "[sev2]"):
        assert part in text, part
    assert body["allowed_mentions"] == {"parse": []}
    kind, summary, data = _last_event(writer, incident)
    assert (kind, summary) == ("action", "Paged priya on Discord")
    assert '"ok":true' in data


def test_without_a_webhook_nothing_is_sent_but_the_attempt_is_logged(writer, incident, monkeypatch):
    monkeypatch.setattr(get_settings(), "discord_webhook_url", None)

    r = tools.page_owner(incident, "priya", "hi")

    assert r.ok is False and "DISCORD_WEBHOOK_URL" in r.detail
    assert "failed" in _last_event(writer, incident)[1]


@pytest.mark.parametrize("sent", [Sent(status=500), Sent(error=httpx.ConnectTimeout("slow"))])
def test_discord_failures_are_reported_not_raised(writer, incident, monkeypatch, sent):
    monkeypatch.setattr(get_settings(), "discord_webhook_url", HOOK)
    monkeypatch.setattr(tools, "_post", sent)

    r = tools.page_owner(incident, "priya", "hi")

    assert r.ok is False and ("500" in r.detail or "ConnectTimeout" in r.detail)


@pytest.mark.parametrize(("iid", "handle"), [("INC-999", "priya"), (None, "nobody")])
def test_bad_input_is_a_tool_error(writer, incident, discord, iid, handle):
    with pytest.raises(ToolError):
        tools.page_owner(iid or incident, handle, "hi")
    assert discord.calls == []
