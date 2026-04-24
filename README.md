# Stanford Eng KB

A minimal RAG pipeline over an Obsidian vault:

```
 .md files  ──►  chunk + embed  ──►  Supabase Postgres + pgvector
                                              │
                                              ▼
                                     hybrid search (vector + FTS, RRF-fused)
                                              │
                                              ▼
                                     Claude answers with citations
                                              │
                                              ▼
                                        MCP server (FastMCP)
```

## Layout

```
stanford-eng-kb/
├── .env.example          # copy to .env and fill in
├── requirements.txt
├── sql/
│   └── schema.sql        # run once in Supabase SQL Editor
└── vault/
    └── app/
        ├── connection.py     # psycopg2 + pgvector adapter
        ├── ingest.py         # walk vault, chunk, embed, upsert
        ├── retrieval.py      # hybrid search w/ RRF
        ├── claude_answer.py  # grounded Q&A with citations
        └── expose_mcp.py     # FastMCP server (tools: search, ask)
```

## Setup

1. **Rotate the Supabase DB password.** The old one was committed into `connection.py`. Go to Supabase dashboard → Project Settings → Database → Reset database password.

2. **Install deps** (Python 3.13 is already on this machine):

   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows / git-bash
   pip install -r requirements.txt
   ```

3. **Create `.env`**:

   ```bash
   cp .env.example .env
   ```

   Fill in: `SUPABASE_DB_HOST` (format: `db.<project-ref>.supabase.co` — no `https://`), the new password, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. `VAULT_PATH` is already pointed at your `EngKB` vault.

4. **Create the schema.** Open Supabase → SQL Editor → paste and run [sql/schema.sql](sql/schema.sql).

## Run

```bash
cd vault/app

# 1. One-off: load/refresh the vault into Postgres
python ingest.py

# 2. Ad-hoc hybrid search
python retrieval.py "what is the plugin kit?"

# 3. Ad-hoc grounded answer
python claude_answer.py "summarise the integrations section"

# 4. Expose as MCP server
python expose_mcp.py
```

To wire the MCP server into Claude Desktop, add to its `mcpServers` config:

```json
{
  "stanford-eng-kb": {
    "command": "/.venv/Scripts/python.exe",
    "args": ["/vault/app/expose_mcp.py"]
  }
}
```

## Design notes

- **Chunking**: `RecursiveCharacterTextSplitter`, 500 chars / 100 overlap. Reasonable default for markdown; tune later.
- **Embeddings**: `text-embedding-3-small` (1536 dims, cheap). If you switch to `-large` (3072 dims), update both `ingest.py` and the `vector(1536)` type in `schema.sql`.
- **Dedup**: `(source, chunk_idx)` is a unique constraint; re-ingest does `ON CONFLICT DO UPDATE`, so edits in Obsidian propagate but order matters. If you rename a file, delete its old rows first.
- **Hybrid search**: Reciprocal Rank Fusion over cosine-ANN (`<=>`) and Postgres FTS (`ts_rank_cd`). `K=60` is the standard RRF constant. Pool of 20 per channel is fine for small vaults.
- **Model**: Claude Opus 4.7 (`claude-opus-4-7`). Swap to `claude-sonnet-4-6` if cost matters.
