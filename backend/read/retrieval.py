"""Hybrid search: vector + full-text, merged with Reciprocal Rank Fusion."""

from backend.shared.connection import get_conn
from backend.shared.embedder import embed_query

# RRF constant — 60 is the value from the original Cormack/Clarke paper.
RRF_K = 60


def hybrid_search(query: str, k: int = 5, pool: int = 20):
    vector = embed_query(query)

    # Fresh connection per call — Supavisor closes idle connections, so a long-lived
    # one breaks on the next request. Cost is negligible at our QPS.
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id, content, metadata,
                   1 - (embedding <=> %s::vector) as similarity
            from documents
            order by embedding <=> %s::vector
            limit %s
            """,
            (vector, vector, pool),
        )
        vector_hits = cur.fetchall()

        cur.execute(
            """
            select id, content, metadata,
                   ts_rank_cd(to_tsvector('english', content),
                              plainto_tsquery('english', %s)) as rank
            from documents
            where to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            order by rank desc
            limit %s
            """,
            (query, query, pool),
        )
        keyword_hits = cur.fetchall()

    # Reciprocal Rank Fusion: score(doc) = sum(1 / (K + rank_in_list))
    scores: dict[int, float] = {}
    rows: dict[int, tuple] = {}

    for rank, row in enumerate(vector_hits):
        doc_id = row[0]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        rows[doc_id] = row

    for rank, row in enumerate(keyword_hits):
        doc_id = row[0]
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        rows.setdefault(doc_id, row)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return [
        {
            "id": doc_id,
            "content": rows[doc_id][1],
            "metadata": rows[doc_id][2],
            "score": score,
        }
        for doc_id, score in ranked
    ]


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "what is this vault about?"
    for hit in hybrid_search(q):
        print(f"[{hit['score']:.4f}] {hit['metadata'].get('source')}")
        print(hit["content"][:200].replace("\n", " "))
        print("---")
