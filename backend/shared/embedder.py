"""Embeddings via OpenAI's text-embedding-3-small.

We request 384-dim vectors so the existing pgvector column (`vector(384)` in
sql/schema.sql) is unchanged. text-embedding-3 models are trained with
Matryoshka representation learning, so truncation to 384 dim performs close to
full 1536-dim on retrieval tasks for small/medium corpora — and keeps the
schema, HNSW index, and migration story simple.

Used by both read (query embedding) and ingest (document embedding); they MUST
share the model + dim so vectors are comparable.

Requires OPENAI_API_KEY in the environment.
"""

from openai import OpenAI

MODEL_NAME = "text-embedding-3-small"
EMBED_DIM = 384

# Lazily initialise so importing this module doesn't fail when the key is
# missing (e.g., during local TodoWrite-only changes / static checks).
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from env
    return _client


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = _get_client().embeddings.create(
        model=MODEL_NAME,
        input=texts,
        dimensions=EMBED_DIM,
    )
    # API returns one item per input, in the same order.
    return [item.embedding for item in resp.data]


def embed_query(text: str) -> list[float]:
    return embed_documents([text])[0]
