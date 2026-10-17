"""The company-brain question format: POST /ask (task B05), answered by the Brain agent (A09)."""

from pydantic import BaseModel, ConfigDict, Field


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500, examples=["Who knows the payments DB?"])


class AskOut(BaseModel):
    answer: str = Field(description="A few sentences, with names and numbers from the graph")
    evidence: list[str] = Field(
        description="Node ids the answer rests on (svc:..., person:..., INC-...), to light up"
    )
