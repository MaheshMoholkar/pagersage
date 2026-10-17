"""T8 record_decision (G14): decision traces with evidence, policies and precedents."""

import pytest

from pagersage.contracts import tools
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import ToolError


def _decide(**kw):
    args = {
        "incident_id": "INC-051",
        "agent": AgentName.INVESTIGATOR,
        "what": "payments-db pool cut is the root cause",
        "why": "top suspect; payments-db is sicker than everything above it",
        "confidence": 0.8,
        "evidence_ids": [],
    }
    return tools.record_decision(**(args | kw))


def _one(g, q, params=None):
    [[v]] = g.ro_query(q, params).result_set
    return v


def test_decision_is_about_the_incident_and_made_by_the_agent(writer):
    did = _decide()

    assert did.startswith("dec:INC-051:")
    row = writer.ro_query(
        "MATCH (d:Decision {id:$did})-[:ABOUT]->(i:Incident), (d)-[:MADE_BY]->(a:Agent) "
        "RETURN i.id, a.id, a.name, a.model, d.what, d.confidence, d.ts > 0",
        {"did": did},
    ).result_set
    assert row == [
        [
            "INC-051",
            "agent:investigator",
            "investigator",
            "claude-sonnet-5-5",
            "payments-db pool cut is the root cause",
            0.8,
            True,
        ]
    ]


def test_ids_count_up_per_incident(writer):
    first, second = _decide(), _decide()

    assert int(second.rsplit(":", 1)[1]) == int(first.rsplit(":", 1)[1]) + 1


def test_evidence_links_any_node_including_commit_shas(writer):
    sha = _one(writer, "MATCH (c:Commit) RETURN c.sha ORDER BY c.sha LIMIT 1")
    did = _decide(evidence_ids=["svc:payments-db", "cfg-0050", sha, "INC-042"])

    linked = writer.ro_query(
        "MATCH (:Decision {id:$did})-[:BASED_ON]->(e) RETURN e.id ORDER BY e.id", {"did": did}
    ).result_set
    assert sorted(r[0] for r in linked) == sorted(["svc:payments-db", "cfg-0050", sha, "INC-042"])


def test_policies_are_linked(writer):
    did = _decide(policy_ids=["pol:tier1-rollback-ack"])

    assert (
        _one(
            writer,
            "MATCH (:Decision {id:$did})-[:APPLIED_POLICY]->(p:Policy) RETURN p.id",
            {"did": did},
        )
        == "pol:tier1-rollback-ack"
    )


def test_empty_evidence_still_links_precedents(writer):
    # A decision on INC-042, which INC-051 is similar to, is a precedent for the new one.
    writer.query(
        "MATCH (old:Incident {id:'INC-042'}), (new:Incident {id:'INC-051'}) "
        "MERGE (new)-[:SIMILAR_TO {score:0.67}]->(old) "
        "CREATE (:Decision {id:'dec:INC-042:1', what:'raise the pool', ts:1})-[:ABOUT]->(old)"
    )

    did = _decide(evidence_ids=[])

    assert (
        _one(
            writer,
            "MATCH (p:Decision)-[:PRECEDENT_FOR]->(:Decision {id:$did}) RETURN p.id",
            {"did": did},
        )
        == "dec:INC-042:1"
    )


@pytest.mark.parametrize(
    "kw",
    [
        {"incident_id": "INC-999"},
        {"confidence": 1.5},
        {"evidence_ids": ["svc:payments-db", "dep-9999"]},
        {"policy_ids": ["pol:nope"]},
    ],
)
def test_bad_input_is_a_tool_error_and_writes_nothing(writer, kw):
    before = _one(writer, "MATCH (d:Decision) RETURN count(d)")

    with pytest.raises(ToolError):
        _decide(**kw)

    assert _one(writer, "MATCH (d:Decision) RETURN count(d)") == before
