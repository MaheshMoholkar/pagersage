"""POST /ask (B05): question in, answer plus evidence node ids out (Brain agent, A09)."""

import pytest

from pagersage.agents import llm
from tests.fake_claude import FakeClaude, reply, use


@pytest.fixture
def claude(monkeypatch):
    def install(*replies):
        fake = FakeClaude(replies)
        monkeypatch.setattr(llm, "client", lambda: fake)
        return fake

    return install


def test_question_in_answer_and_evidence_out(api, tool_graph, claude):
    claude(
        reply(use("who_knows", service_id="svc:payments-db", limit=5)),
        reply(use("answer", answer="priya", evidence_ids=["svc:payments-db", "person:priya"])),
    )

    r = api.post("/ask", json={"question": "Who knows the payments DB?"})

    assert r.status_code == 200
    assert r.json() == {"answer": "priya", "evidence": ["svc:payments-db", "person:priya"]}


@pytest.mark.parametrize("body", [{"question": ""}, {}, {"question": "x", "extra": 1}])
def test_bad_questions_are_422(api, body):
    assert api.post("/ask", json=body).status_code == 422


def test_no_api_key_is_503(api, monkeypatch):
    def no_key():
        raise llm.AgentError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(llm, "client", no_key)

    r = api.post("/ask", json={"question": "Which services are fragile?"})

    assert r.status_code == 503
    assert r.json() == {"error": "ANTHROPIC_API_KEY is not set"}
