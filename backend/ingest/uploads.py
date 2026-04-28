"""Customer-facing ingest: one uploaded file (or pasted text) becomes one row in
`documents_raw` + N rows in `documents`, all stamped with org metadata.

Called by the /api/ingest/upload endpoint. This is the only ingest path the
deployed backend exposes; pipeline.py remains as an optional local CLI for
one-time bulk seeding from a folder.
"""

import logging
import uuid
from datetime import datetime, timezone

from psycopg2.extras import Json, execute_batch

from backend.shared.connection import get_conn
from backend.shared.embedder import embed_documents

from .chunker import chunk_text
from .extractors import extract_text

logger = logging.getLogger(__name__)


def ingest_upload(
    *,
    org_id: str,
    sub_id: str,
    text: str | None = None,
    file_name: str | None = None,
    file_bytes: bytes | None = None,
) -> dict:
    """Ingest exactly one upload (either pasted text OR a file).

    Returns a summary: { raw_id, source, chunks, characters }.

    Synthesises a unique `source` so repeated uploads of the same filename
    across orgs/customers don't collide on the `documents.source` uniqueness
    constraint.
    """
    if (text is None) == (file_bytes is None):
        raise ValueError("Provide exactly one of: text, file_bytes")

    if file_bytes is not None:
        if not file_name:
            raise ValueError("file_name is required when file_bytes is given")
        body = extract_text(file_name, file_bytes)
        original_name = file_name
    else:
        body = (text or "").strip()
        original_name = None

    if not body:
        raise ValueError("Extracted content is empty")

    upload_id = str(uuid.uuid4())
    source = f"{org_id}/{sub_id}/{upload_id}"
    if original_name:
        source = f"{source}__{original_name}"

    base_meta = {
        "org_id": org_id,
        "sub_id": sub_id,
        "source_type": "upload",
        "original_name": original_name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "uploads.extracted org=%s sub=%s source=%s chars=%d",
        org_id, sub_id, source, len(body),
    )

    chunks = chunk_text(body, source=source, extra_metadata=base_meta)
    if not chunks:
        raise ValueError("Chunker produced no chunks")
    logger.info("uploads.chunked source=%s chunks=%d", source, len(chunks))

    vectors = embed_documents([c.content for c in chunks])
    logger.info("uploads.embedded source=%s vectors=%d", source, len(vectors))
    chunk_rows = [
        (c.source, c.chunk_idx, c.content, Json(c.metadata), v)
        for c, v in zip(chunks, vectors)
    ]
    raw_row = (
        org_id, sub_id, source, "upload", original_name, body, Json(base_meta),
    )

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into documents_raw
                (org_id, sub_id, source, source_type, original_name, content, metadata)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (source) do update set
                content     = excluded.content,
                metadata    = excluded.metadata,
                uploaded_at = now()
            returning id
            """,
            raw_row,
        )
        raw_id = cur.fetchone()[0]

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
            chunk_rows,
            page_size=100,
        )
        conn.commit()

    logger.info(
        "uploads.persisted source=%s raw_id=%d chunks=%d",
        source, raw_id, len(chunks),
    )

    return {
        "raw_id": raw_id,
        "source": source,
        "chunks": len(chunks),
        "characters": len(body),
    }
