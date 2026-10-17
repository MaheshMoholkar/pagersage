"""POST /ask: a company-brain question in, an answer plus evidence node ids out (task B05),
answered by the Brain agent (A09). The UI lights the evidence on the graph canvas."""

from fastapi import APIRouter

from pagersage.agents import brain
from pagersage.contracts.ask import AskIn, AskOut

router = APIRouter(tags=["ask"])


@router.post("/ask")
def post_ask(body: AskIn) -> AskOut:
    return brain.ask(body.question)
