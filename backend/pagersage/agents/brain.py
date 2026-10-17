"""Company brain (task A09): answer a question about Kestrel Pay from the graph.

The Brain agent gets only read tools (AGENT_TOOLS[brain]) plus `answer`, which ends the run
with the answer and the node ids it rests on. Evidence ids must exist in the graph, so the UI
can light them up; an unknown id comes back as an error for the agent to fix. There is no
incident, so nothing is written and no events are emitted.
"""

from typing import Any

from pagersage import db, queries
from pagersage.agents import llm, prompts, registry
from pagersage.contracts.ask import AskOut
from pagersage.contracts.schema import AgentName

ANSWER = {
    "name": "answer",
    "description": "Give the final answer. Call once, last.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "Two to five sentences"},
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Node ids the answer rests on: svc:..., person:<handle>, INC-...",
            },
        },
        "required": ["answer", "evidence_ids"],
        "additionalProperties": False,
    },
    "strict": True,
}


class BrainError(Exception):
    """The Brain could not answer (no API key, refusal, cap, timeout)."""


def _answer_tool(out: dict[str, AskOut]) -> llm.Tool:
    def run(raw: dict[str, Any]) -> llm.ToolOutcome:
        evidence = list(dict.fromkeys(raw.get("evidence_ids") or []))
        if evidence:
            found = db.get_graph().ro_query(queries.load("nodes_exist"), {"ids": evidence})
            if missing := [nid for nid, n in found.result_set if not n]:
                return llm.ToolOutcome(
                    f"Unknown evidence ids {missing}: use ids exactly as tools returned them "
                    "(people as person:<handle>).",
                    is_error=True,
                )
        out["answer"] = AskOut(answer=str(raw.get("answer", "")).strip(), evidence=evidence)
        return llm.ToolOutcome('{"ok": true}')

    return llm.Tool(name="answer", definition=ANSWER, run=run)


def ask(question: str, api: Any = None) -> AskOut:
    out: dict[str, AskOut] = {}
    ctx = registry.RunContext(AgentName.BRAIN)
    question = question.replace("<", "&lt;").replace(">", "&gt;")
    try:
        result = llm.run(
            AgentName.BRAIN,
            prompts.system(AgentName.BRAIN),
            f"<question>{question}</question>",
            [*registry.tools_for(ctx), _answer_tool(out)],
            finish={"answer"},
            api=api,
        )
    except llm.AgentError as e:
        raise BrainError(str(e)) from e
    if not result.ok or "answer" not in out:
        raise BrainError(f"The brain could not answer ({result.stop}).")
    return out["answer"]
