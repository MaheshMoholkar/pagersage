"""A scripted stand-in for anthropic.Anthropic, so agent tests never call the API.

api = FakeClaude([reply(thinking("..."), use("find_service", q="checkout")), reply(text("ok"))])
llm.run(..., api=api)
api.requests  # every messages.create(**kwargs), messages copied at call time
"""

import copy
import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


def text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def thinking(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking=t, signature="sig")


def use(name: str, **input) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=name, input=input)


def reply(*content, stop_reason: str | None = None) -> SimpleNamespace:
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
    return SimpleNamespace(content=list(content), stop_reason=stop_reason)


class FakeClaude:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        kwargs["messages"] = copy.copy(kwargs["messages"])
        self.requests.append(kwargs)
        if not self.replies:
            raise AssertionError("FakeClaude ran out of scripted replies")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
