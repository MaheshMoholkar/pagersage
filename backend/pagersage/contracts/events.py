"""The agent event: one line on the incident timeline.

Emitted for every tool call, finding, decision, handoff and action (task A11), streamed to
the UI over SSE (task B04), and stored as an (:Event)-[:PART_OF]->(:Incident) node chained
with NEXT, so the timeline survives restarts and is episodic memory.
"""

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pagersage.contracts.schema import AgentName, event_id


class EventKind(StrEnum):
    STATUS = "status"  # incident opened, status changed, agent started
    TOOL_CALL = "tool_call"  # agent called a tool; data = {tool, input}
    TOOL_RESULT = "tool_result"  # tool returned; data = {tool, ok, rows}
    FINDING = "finding"  # agent concluded something with evidence
    DECISION = "decision"  # Decision node written; data = {decision_id, confidence}
    HANDOFF = "handoff"  # data = {from, to, note}
    ACTION = "action"  # page / issue / rollback; data = {action, ok, url?}
    ERROR = "error"  # tool error, refusal, cap or timeout


class Highlight(BaseModel):
    """What the graph canvas lights up for this event."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[str] = Field(default_factory=list, description="Node ids to highlight")
    edges: list[tuple[str, str, str]] = Field(
        default_factory=list, description="(from_id, REL_TYPE, to_id) triples to highlight"
    )


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    seq: int = Field(ge=1, description="1, 2, 3... per incident; the SSE id")
    ts: int = Field(description="Epoch seconds")
    agent: AgentName | None = Field(default=None, description="None for system events")
    kind: EventKind
    summary: str = Field(max_length=300, description="One line for the timeline")
    data: dict[str, Any] = Field(default_factory=dict)
    highlight: Highlight = Field(default_factory=Highlight)

    @property
    def id(self) -> str:
        return event_id(self.incident_id, self.seq)

    def to_sse(self) -> str:
        """One SSE message. `id` is seq so a reconnecting EventSource resumes after it."""
        return f"id: {self.seq}\nevent: agent\ndata: {self.model_dump_json()}\n\n"

    def to_node_props(self) -> dict[str, Any]:
        """Properties for the Event node. Maps are stored as JSON strings."""
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "seq": self.seq,
            "ts": self.ts,
            "agent": self.agent.value if self.agent else None,
            "kind": self.kind.value,
            "text": self.summary,
            "data": json.dumps(self.data, separators=(",", ":")),
            "highlight": self.highlight.model_dump_json(),
        }

    @classmethod
    def from_node_props(cls, props: dict[str, Any]) -> "AgentEvent":
        return cls(
            incident_id=props["incident_id"],
            seq=props["seq"],
            ts=props["ts"],
            agent=props.get("agent"),
            kind=props["kind"],
            summary=props["text"],
            data=json.loads(props.get("data") or "{}"),
            highlight=Highlight.model_validate_json(props.get("highlight") or "{}"),
        )
