"""Incident embeddings (task G04): all-MiniLM-L6-v2 through fastembed (ONNX, no PyTorch).

Past and new incidents are embedded from the same text (`incident_text`), so the vector index
compares like with like. Vectors are unit length and 384-dim, matching the cosine index
(`indexes.EMBEDDING_DIM`); `db.idx.vector.queryNodes` returns cosine distance.

The model (~90 MB) downloads on first use into $FASTEMBED_CACHE_PATH, or the system temp
directory when that is unset.
"""

from functools import cache

from fastembed import TextEmbedding

from pagersage.indexes import EMBEDDING_DIM

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@cache
def _model() -> TextEmbedding:
    return TextEmbedding(MODEL)


def incident_text(title: str, summary: str) -> str:
    """The text an incident is embedded from. Use it for past and new incidents alike."""
    return f"{title}\n{summary}"


def embed(texts: list[str]) -> list[list[float]]:
    """One unit-length 384-dim vector per text, as plain floats ready for vecf32($v)."""
    vectors = [v.tolist() for v in _model().embed(texts)]
    if vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise RuntimeError(f"{MODEL} returned {len(vectors[0])} dims, index has {EMBEDDING_DIM}")
    return vectors
