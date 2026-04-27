"""End-to-end ingest: load documents → chunk → embed → upsert into Postgres.

Run locally:

    python -m backend.ingest.pipeline

Reads SUPABASE_DB_*, ANTHROPIC_API_KEY, and VAULT_PATH from .env.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg2.extras import Json, execute_batch

from backend.shared.connection import get_conn
from backend.shared.embedder import embed_documents

from .chunker import Chunk, chunk_text
from .vault_loader import LocalVaultLoader, VaultLoader

load_dotenv()


def _chunk_all(loader: VaultLoader) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in loader.iter_documents():
        chunks.extend(chunk_text(doc.text, source=doc.source))
    return chunks


def upsert_chunks(chunks: list[Chunk]) -> int:
    if not chunks:
        return 0

    vectors = embed_documents([c.content for c in chunks])
    rows = [
        (c.source, c.chunk_idx, c.content, Json(c.metadata), v)
        for c, v in zip(chunks, vectors)
    ]

    with get_conn() as conn, conn.cursor() as cur:
        execute_batch(
            cur,
            """
            insert into documents (source, chunk_idx, content, metadata, embedding)
            values (%s, %s, %s, %s, %s)
            on conflict on constraint documents_source_chunk_uq
            do update set
                content   = excluded.content,
                metadata  = excluded.metadata,
                embedding = excluded.embedding
            """,
            rows,
            page_size=100,
        )
        conn.commit()
    return len(rows)


def run_ingest(loader: VaultLoader) -> int:
    return upsert_chunks(_chunk_all(loader))


if __name__ == "__main__":
    vault_path = Path(os.environ["VAULT_PATH"])
    loader = LocalVaultLoader(vault_path)
    n = run_ingest(loader)
    print(f"Upserted {n} chunks from {vault_path}")
