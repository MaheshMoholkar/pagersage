"""T9 handoff (G15): one call writes the Handoff, the timeline Event, the shared state and the
assignment, in one statement."""

import itertools
import json

import pytest

from pagersage.contracts import tools
from pagersage.contracts.events import AgentEvent, EventKind
from pagersage.contracts.schema import AgentName
from pagersage.contracts.tools import ToolError

TRI, INV, HIS = AgentName.TRIAGE, AgentName.INVESTIGATOR, AgentName.HISTORIAN
_ids = itertools.count(60)


@pytest.fixture
def incident(writer):
    """A fresh open incident per test (the module shares one graph)."""
    iid = f"INC-{next(_ids):03d}"
    writer.query("CREATE (:Incident {id:$id, title:'t', status:'investigating'})", {"id": iid})
    return iid


def _rows(g, q, iid):
    return g.ro_query(q, {"iid": iid}).result_set


def test_handoff_node_links_from_to_and_incident(writer, incident):
    hid = tools.handoff(incident, TRI, INV, "payments-db looks sick", {"severity": "sev1"})

    assert hid == f"ho:{incident}:1"
    assert _rows(
        writer,
        "MATCH (h:Handoff)-[:ON]->(:Incident {id:$iid}), (h)-[:FROM]->(f:Agent), (h)-[:TO]->(t) "
        "RETURN h.id, f.name, t.name, h.note, h.ts > 0",
        incident,
    ) == [[hid, "triage", "investigator", "payments-db looks sick", True]]


def test_assignment_flips_to_the_receiving_agent(writer, incident):
    tools.handoff(incident, TRI, INV, "over to you", {})
    tools.handoff(incident, INV, HIS, "cause found", {})

    assert _rows(
        writer, "MATCH (:Incident {id:$iid})-[:ASSIGNED_TO]->(a) RETURN a.id", incident
    ) == [["agent:historian"]]


def test_state_patches_merge(writer, incident):
    tools.handoff(incident, TRI, INV, "a", {"severity": "sev1", "path": ["svc:checkout-api"]})
    tools.handoff(incident, INV, HIS, "b", {"severity": "sev2", "cause": "cfg-0061"})

    [[state]] = _rows(writer, "MATCH (i:Incident {id:$iid}) RETURN i.state", incident)
    assert json.loads(state) == {
        "severity": "sev2",
        "path": ["svc:checkout-api"],
        "cause": "cfg-0061",
    }


def test_each_handoff_appends_a_chained_event(writer, incident):
    tools.handoff(incident, TRI, INV, "first", {})
    tools.handoff(incident, INV, HIS, "second", {})

    rows = _rows(
        writer,
        "MATCH (e:Event)-[:PART_OF]->(:Incident {id:$iid}) RETURN properties(e) ORDER BY e.seq",
        incident,
    )
    events = [AgentEvent.from_node_props(r[0]) for r in rows]
    assert [(e.seq, e.kind, e.agent, e.summary) for e in events] == [
        (1, EventKind.HANDOFF, TRI, "first"),
        (2, EventKind.HANDOFF, INV, "second"),
    ]
    assert events[1].data == {"from": "investigator", "to": "historian", "note": "second"}
    assert _rows(
        writer,
        "MATCH (a:Event)-[:NEXT]->(b:Event)-[:PART_OF]->(:Incident {id:$iid}) RETURN a.seq, b.seq",
        incident,
    ) == [[1, 2]]


def test_long_notes_are_kept_whole_on_the_handoff(writer, incident):
    note = "x" * 500
    tools.handoff(incident, TRI, INV, note, {})

    [[kept, summary]] = _rows(
        writer,
        "MATCH (h:Handoff)-[:ON]->(i:Incident {id:$iid}), (e:Event)-[:PART_OF]->(i) "
        "RETURN h.note, e.text",
        incident,
    )
    assert kept == note and len(summary) == 300


@pytest.mark.parametrize(
    ("iid", "frm", "to", "patch"),
    [
        ("INC-999", TRI, INV, {}),  # unknown incident
        (None, TRI, TRI, {}),  # to itself
        (None, TRI, INV, {"bad": {1, 2}}),  # not JSON
    ],
)
def test_bad_input_is_a_tool_error_and_writes_nothing(writer, incident, iid, frm, to, patch):
    with pytest.raises(ToolError):
        tools.handoff(iid or incident, frm, to, "note", patch)

    assert _rows(writer, "MATCH (h:Handoff)-[:ON]->(:Incident {id:$iid}) RETURN h", incident) == []
