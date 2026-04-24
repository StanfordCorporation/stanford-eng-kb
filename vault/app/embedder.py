"""Local embeddings via sentence-transformers.

Model: all-MiniLM-L6-v2 (384-dim, small, fast). Matches vector(384) in schema.sql.
First import downloads ~90 MB model weights into the HF cache; subsequent runs
load from disk.
"""

from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_documents(texts: list[str]) -> list[list[float]]:
    vecs = _model().encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    return vecs.tolist()


def embed_query(text: str) -> list[float]:
    return embed_documents([text])[0]
