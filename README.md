# Stanford Eng KB

A minimal RAG pipeline over an Obsidian vault:

```
 .md files  ──►  chunk + embed (local MiniLM)  ──►  Supabase Postgres + pgvector
                                                             │
                                                             ▼
                                                    hybrid search (vector + FTS, RRF-fused)
                                                             │
                                                             ▼
                                                    Claude answers with citations
                                                             │
                                              ┌──────────────┼──────────────┐
                                              ▼                             ▼
                                     FastAPI (HTTP + SSE)           FastMCP (stdio)
                                              │
                                              ▼
                                       React/Vite SPA
```

## Layout

```
stanford-eng-kb/
├── .env.example              # copy to .env for local dev
├── .github/workflows/
│   └── deploy.yml            # CI/CD (frontend-only Vercel deploy)
├── .vercelignore
├── api/
│   └── index.py              # FastAPI ASGI app (run with uvicorn)
├── backend/                  # Python library, split into read / ingest / shared
│   ├── shared/               # used by BOTH halves; stays in every service after a split
│   │   ├── connection.py     # psycopg2 + pgvector, per-request connections
│   │   └── embedder.py       # sentence-transformers MiniLM (384 dim) — query AND doc
│   ├── read/                 # query path (read-only)
│   │   ├── retrieval.py      # hybrid search w/ RRF
│   │   └── claude_answer.py  # grounded Q&A, streaming
│   ├── ingest/               # write path (chunk + embed + upsert)
│   │   ├── chunker.py        # single source of truth for chunk boundaries
│   │   ├── vault_loader.py   # pluggable doc source (Local today; Git/S3 later)
│   │   └── pipeline.py       # load → chunk → embed → upsert orchestrator
│   └── expose_mcp.py         # FastMCP server (read-only)
├── frontEnd/                 # React/Vite SPA
├── sql/schema.sql            # run once in Supabase SQL Editor
├── vault/                    # your Obsidian notes (local-only)
├── requirements.txt
└── vercel.json
```

## Setup

1. **Rotate the Supabase DB password.** The old one was committed into `connection.py`. Supabase dashboard → Project Settings → Database → Reset database password.

2. **Install deps** (Python 3.13 OK locally):

   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows / git-bash
   pip install -r requirements.txt
   ```

3. **Create `.env`** from [.env.example](.env.example). Fill in Supabase host/password, `ANTHROPIC_API_KEY`, and `VAULT_PATH`. (`OPENAI_API_KEY` is only needed if you later swap back to hosted embeddings.)

4. **Create the schema.** Supabase → SQL Editor → paste and run [sql/schema.sql](sql/schema.sql).

## Run

```bash
# 1. One-off: load/refresh the vault into Postgres
python -m backend.ingest.pipeline

# 2. Ad-hoc hybrid search
python -m backend.read.retrieval "what is the plugin kit?"

# 3. Ad-hoc grounded answer
python -m backend.read.claude_answer "summarise the integrations section"

# 4. HTTP API for the frontend
uvicorn api.index:app --reload --port 8000

# 5. MCP server (stdio) — for Claude Desktop / Cursor
python -m backend.expose_mcp

# 6. Frontend (separate terminal)
cd frontEnd && npm install && npm run dev
```

MCP config for Claude Desktop:

```json
{
  "stanford-eng-kb": {
    "command": "c:/Users/AkshitMahajanStanfor/stanford-innovations/stanford-eng-kb/.venv/Scripts/python.exe",
    "args": ["-m", "backend.expose_mcp"],
    "cwd": "c:/Users/AkshitMahajanStanfor/stanford-innovations/stanford-eng-kb"
  }
}
```

## Deploy

Production split: **Vercel** (static frontend) → **Railway** (FastAPI backend) → **Supabase** (pgvector).

The Python backend can't run on Vercel because `sentence-transformers` + `torch` (~1 GB) exceed Vercel's 250 MB serverless-function size limit. Railway runs containers, so it's fine.

### 1. Backend on Railway

[Dockerfile](Dockerfile) and [railway.json](railway.json) are checked in. The Dockerfile pre-downloads MiniLM weights at build time so cold starts are warm.

1. **New Project → Deploy from GitHub** → select this repo. Railway detects the Dockerfile and builds (~3–5 min).
2. **Variables** — set:
   - `SUPABASE_DB_HOST` (use the **pooler** endpoint, e.g. `aws-0-<region>.pooler.supabase.com`)
   - `SUPABASE_DB_PORT=6543`
   - `SUPABASE_DB_NAME=postgres`
   - `SUPABASE_DB_USER=postgres.<project-ref>`
   - `SUPABASE_DB_PASSWORD`
   - `ANTHROPIC_API_KEY`
   - `FRONTEND_ORIGIN` (set after Vercel deploy, comma-separated for preview + prod URLs)
3. **Settings → Networking → Generate Domain.** Note the URL.
4. **Settings → Resources** — switch off Hobby (512 MB OOMs under torch). Pro/Trial gives 8 GB.
5. Smoke: `curl https://<railway-url>/api/health` → `{"ok":true}`.

### 2. Frontend on Vercel

[vercel.json](vercel.json) is a static build only.

1. **Import Project** → select this repo. Build settings auto-load.
2. **Environment Variables** → `VITE_API_URL=https://<railway-url>` (no trailing slash).
3. Deploy. Note the Vercel URL.
4. Back to Railway → set `FRONTEND_ORIGIN=https://<vercel-url>` and let it redeploy.
5. **Project → Deployment Protection** → enable password protection while in soft launch (no per-user auth yet).

### 3. Seed the data

The vault is still local for v1. From your machine, with `.env` pointing at the prod Supabase pooler:

```bash
python -m backend.ingest.pipeline
```

Re-run whenever your notes change. Git-backed vault + webhook-triggered re-ingest is the next iteration.

## Design notes

- **Chunking**: `RecursiveCharacterTextSplitter`, 500 chars / 100 overlap.
- **Embeddings**: `all-MiniLM-L6-v2` (384 dim) via `sentence-transformers`. Local, free, and good enough for small vaults. First run downloads ~90 MB of weights.
- **Dedup**: `(source, chunk_idx)` is a unique constraint; re-ingest does `ON CONFLICT DO UPDATE`. If you rename a file, delete its old rows first.
- **Hybrid search**: Reciprocal Rank Fusion over cosine-ANN (`<=>`) and Postgres FTS (`ts_rank_cd`). `K=60` from the Cormack/Clarke paper.
- **Streaming**: SSE over FastAPI `StreamingResponse`. `X-Accel-Buffering: no` disables proxy buffering.
- **Model**: Claude Opus 4.7 for answers, Haiku 4.5 for query rewrites.
- **Serverless connections**: [backend/shared/connection.py](backend/shared/connection.py) opens a fresh connection per request — correct for any serverless deploy (kept for when/if you swap to OpenAI embeddings and move backend to Vercel).
- **Read/ingest seam**: `backend/` is split so the read path and ingest path can be deployed as separate services later without rewriting code. The contract: `backend.read` and `backend.ingest` may both import from `backend.shared`, but **must not** import from each other. Entry points (`api/`, `backend.expose_mcp`, future `worker/`) are the only places that compose both halves. Splitting into a worker is then a directory copy, not a refactor.
