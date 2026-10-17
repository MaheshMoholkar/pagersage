"""Scribe (A08): on resolve, write the postmortem, the runbook outcome (3/3 -> 4/4 for the demo)
and the incident embedding, closing the memory loop."""

import itertools

import pytest

from pagersage.agents import orchestrator
from pagersage.contracts import tools
from pagersage.contracts.tools import ToolError
from tests.fake_claude import FakeClaude, reply, use

RB = "rb:raise-payments-db-pool"
_ids = itertools.count(30)


@pytest.fixture
def resolved(writer):
    """A fresh resolved incident on payments-db."""
    iid = f"INC-1{next(_ids):02d}"
    writer.query(
        "MATCH (s:Service {id:'svc:payments-db'}) "
        "CREATE (i:Incident {id:$id, title:'checkout-api errors: payments-db pool exhausted', "
        "severity:'sev1', status:'resolved', opened_at:1792500000, resolved_at:1792501800, "
        "summary:'Raised max_pool_size on payments-db back to 100 with the runbook.'}), "
        "(i)-[:AFFECTED]->(s)",
        {"id": iid},
    )
    return iid


def _counts(g, rb=RB):
    return g.ro_query(
        "MATCH (rb:Runbook {id:$rb}) RETURN rb.success_count, rb.fail_count", {"rb": rb}
    ).result_set[0]


def test_runbook_outcome_goes_from_3_of_3_to_4_of_4(writer, resolved):
    before = _counts(writer)

    tools.record_runbook_outcome(RB, resolved, True)
    tools.record_runbook_outcome(RB, resolved, True)  # again: no double count

    assert before == [3, 0]
    assert _counts(writer) == [4, 0]
    assert tools.best_runbook("svc:payments-db")[0].success_count == 4


def test_a_failed_runbook_counts_as_a_failure(writer, resolved):
    before = _counts(writer, "rb:failover-payments-db")

    tools.record_runbook_outcome("rb:failover-payments-db", resolved, False)

    assert _counts(writer, "rb:failover-payments-db") == [before[0], before[1] + 1]


def test_postmortem_is_written_by_the_scribe_and_refreshes_the_embedding(writer, resolved):
    pid = tools.write_postmortem(resolved, "Pool cut exhausted payments-db", "## Summary\n...")

    assert pid == f"pm:{resolved}"
    [[title, agent, embedded]] = writer.ro_query(
        "MATCH (a:Agent)-[:WROTE]->(pm:Postmortem)-[:ABOUT]->(i:Incident {id:$i}) "
        "RETURN pm.title, a.name, i.embedding IS NOT NULL",
        {"i": resolved},
    ).result_set
    assert (title, agent, embedded) == ("Pool cut exhausted payments-db", "scribe", True)
    tools.write_postmortem(resolved, "Pool cut (v2)", "body")  # again: replaced, not duplicated
    assert writer.ro_query(
        "MATCH (pm:Postmortem)-[:ABOUT]->(:Incident {id:$i}) RETURN pm.title", {"i": resolved}
    ).result_set == [["Pool cut (v2)"]]


def test_the_next_incident_finds_this_one(writer, resolved):
    tools.write_postmortem(resolved, "Pool cut exhausted payments-db", "body")
    writer.query("CREATE (:Incident {id:'INC-199', status:'open', opened_at:1792600000})")
    tools.set_triage(
        "INC-199",
        "checkout-api errors: payments-db connection pool exhausted",
        "sev1",
        ["svc:payments-db"],
        "payments-svc cannot get connections from payments-db; checkout fails.",
    )

    found = tools.similar_incidents("INC-199", ["svc:payments-db"], limit=10)

    assert resolved in [i.id for i in found.vector_only]


@pytest.mark.parametrize(
    ("call", "hint"),
    [
        (lambda iid: tools.write_postmortem("INC-999", "t", "b"), "No incident"),
        (lambda iid: tools.write_postmortem(iid, " ", "b"), "empty"),
        (lambda iid: tools.record_runbook_outcome("rb:nope", iid, True), "best_runbook"),
        (lambda iid: tools.record_runbook_outcome(RB, "INC-999", True), "No incident"),
    ],
)
def test_bad_input_is_a_tool_error(writer, resolved, call, hint):
    with pytest.raises(ToolError, match=hint):
        call(resolved)


def test_postmortems_wait_for_resolve(writer):
    writer.query("CREATE (:Incident {id:'INC-198', status:'investigating'})")

    with pytest.raises(ToolError, match="not resolved"):
        tools.write_postmortem("INC-198", "t", "b")


def test_scribe_agent_closes_the_memory_loop(writer, resolved):
    before = _counts(writer)
    api = FakeClaude(
        [
            reply(use("replay_incident")),
            reply(use("best_runbook", service_id="svc:payments-db", limit=3)),
            reply(use("record_runbook_outcome", runbook_id=RB, worked=True)),
            reply(use("write_postmortem", title="Pool cut exhausted payments-db", body="...")),
        ]
    )

    assert orchestrator.run_scribe(resolved, api=api) is True

    assert _counts(writer) == [before[0] + 1, before[1]]
    assert writer.ro_query(
        "MATCH (pm:Postmortem {id:$p}) RETURN count(pm)", {"p": f"pm:{resolved}"}
    ).result_set == [[1]]
    kinds = writer.ro_query(
        "MATCH (e:Event {incident_id:$i}) RETURN e.kind ORDER BY e.seq", {"i": resolved}
    ).result_set
    assert [k[0] for k in kinds] == ["status", "tool_call", "tool_call", "finding", "finding"]
