"""Hybrid search: vector + full-text, merged with Reciprocal Rank Fusion.

Multi-tenancy: queries MUST pass `org_id` to scope results to one tenant.
Passing `org_id=None` disables the filter — only safe for admin / internal use,
never on a customer-facing path.

Shared content: rows with `metadata->>'org_id' = SHARED_ORG_ID` are visible to
every tenant, regardless of sub_id. Used for cross-org seed/baseline content.
Customers can't write to it through the UI; only the operator (via the bulk CLI)
can put rows in the shared bucket.
"""

from backend.shared.connection import get_conn
from backend.shared.embedder import embed_query

# RRF constant — 60 is the value from the original Cormack/Clarke paper.
RRF_K = 60

# Sentinel org_id for cross-tenant content. Underscore prefix avoids collision
# with any real org slug from the UI taxonomy.
SHARED_ORG_ID = "_shared"


def _tenant_filter(org_id: str | None, sub_id: str | None) -> tuple[str, tuple]:
    """Build a SQL fragment + params for tenant scoping.

    A row matches if EITHER:
      • its org_id is the shared sentinel (universal content), OR
      • its org_id matches the caller's org_id (and sub_id, if provided).
    """
    if org_id is None:
        return "", ()

    if sub_id is None:
        clause = "(metadata->>'org_id' = %s OR metadata->>'org_id' = %s)"
        return clause, (SHARED_ORG_ID, org_id)

    clause = (
        "(metadata->>'org_id' = %s "
        "OR (metadata->>'org_id' = %s AND metadata->>'sub_id' = %s))"
    )
    return clause, (SHARED_ORG_ID, org_id, sub_id)


def hybrid_search(
    query: str,
    k: int = 5,
    pool: int = 20,
    *,
    org_id: str | None = None,
    sub_id: str | None = None,
):
    vector = embed_query(query)
    tenant_sql, tenant_params = _tenant_filter(org_id, sub_id)

    vector_where = f"where {tenant_sql}" if tenant_sql else ""
    fts_where_clauses = [*([tenant_sql] if tenant_sql else []),
                         "to_tsvector('english', content) @@ plainto_tsquery('english', %s)"]
    fts_where = "where " + " and ".join(fts_where_clauses)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            select id, content, metadata,
                   1 - (embedding <=> %s::vector) as similarity
            from documents
            {vector_where}
            order by embedding <=> %s::vector
            limit %s
            """,
            (vector, *tenant_params, vector, pool),
        )
        vector_hits = cur.fetchall()

        cur.execute(
            f"""
            select id, content, metadata,
                   ts_rank_cd(to_tsvector('english', content),
                              plainto_tsquery('english', %s)) as rank
            from documents
            {fts_where}
            order by rank desc
            limit %s
            """,
            (query, *tenant_params, query, pool),
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
