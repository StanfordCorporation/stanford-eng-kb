"""Walk the Obsidian vault, chunk each markdown note, embed, upsert into Postgres."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg2.extras import Json, execute_batch

from connection import conn, cur
from embedder import embed_documents

load_dotenv()

VAULT_PATH = Path(os.environ["VAULT_PATH"])

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
)


def load_docs():
    docs = []
    for path in VAULT_PATH.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(VAULT_PATH)).replace("\\", "/")
        for i, chunk in enumerate(splitter.split_text(text)):
            docs.append({
                "source": rel,
                "chunk_idx": i,
                "content": chunk,
                "metadata": {"source": rel, "chunk": i},
            })
    return docs


def insert_docs(docs):
    if not docs:
        return 0

    vectors = embed_documents([d["content"] for d in docs])

    rows = [
        (d["source"], d["chunk_idx"], d["content"], Json(d["metadata"]), v)
        for d, v in zip(docs, vectors)
    ]

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


if __name__ == "__main__":
    docs = load_docs()
    print(f"Loaded {len(docs)} chunks from {VAULT_PATH}")
    n = insert_docs(docs)
    print(f"Upserted {n} rows into documents")
