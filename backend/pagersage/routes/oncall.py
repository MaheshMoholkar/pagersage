"""GET /oncall: who is on call now, one person per team (the web top bar)."""

from fastapi import APIRouter

from pagersage import oncall
from pagersage.oncall import OnCallNow

router = APIRouter(tags=["oncall"])


@router.get("/oncall")
def get_on_call(at: int | None = None) -> list[OnCallNow]:
    """Each team's on-call person now, or at `?at=` (epoch seconds)."""
    return oncall.on_call_now(at)
