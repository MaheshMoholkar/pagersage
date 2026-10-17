"""Who is on call now, one person per team (the web top bar). Read-only."""

import time

from pydantic import BaseModel, Field

from pagersage import db, queries


class OnCallNow(BaseModel):
    team: str
    handle: str
    name: str
    until: int = Field(description="When the shift ends (epoch seconds, exclusive)")


def on_call_now(now: int | None = None) -> list[OnCallNow]:
    """Each team's on-call person at `now` (default: the current time), by team name."""
    rows = (
        db.get_graph()
        .ro_query(queries.load("on_call_now"), {"now": int(time.time()) if now is None else now})
        .result_set
    )
    return [OnCallNow(team=t, handle=h, name=n, until=u) for t, h, n, u in rows]
