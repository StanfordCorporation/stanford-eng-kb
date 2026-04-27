# Stanford KB

Multi-tenant RAG: customers upload `.md`/`.txt`/`.pdf`/`.docx` files (or paste text)
into an org/sub-org silo, and chat against their own slice of the knowledge base.

```
 file or text upload (per org)  ──►  extract → chunk → embed (local MiniLM)
                                                ▼
                                  Supabase Postgres + pgvector (filtered by org_id)
                                                ▼
                                  hybrid search (vector + FTS, RRF-fused)
                                                ▼
                                  Claude answers with citations
                                                ▼
                                  FastAPI (HTTP + SSE)  │  FastMCP (stdio)
                                                ▼
                                  React/Vite SPA
```

## Layout

```
stanford-eng-kb/
├── .env.example              # copy to .env for local dev
├── .dockerignore
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
│   ├── ingest/               # write path (one upload at a time)
│   │   ├── chunker.py        # single source of truth for chunk boundaries
│   │   ├── extractors.py     # md/txt/pdf/docx → plain text
│   │   ├── uploads.py        # one upload → documents_raw + documents (with org metadata)
│   │   └── pipeline.py       # bulk-upload CLI (client; POSTs to /api/ingest/upload)
│   └── expose_mcp.py         # FastMCP server (read-only)
├── frontEnd/                 # React/Vite SPA
├── sql/schema.sql            # run once in Supabase SQL Editor
├── vault/                    # legacy local notes (optional, used only by bulk CLI)
├── Dockerfile                # Railway image (backend)
├── railway.json              # Railway build/deploy config
├── requirements.txt
└── vercel.json               # Vercel static-build config (frontend)
```

## Setup

1. **Rotate the Supabase DB password.** The old one was committed into `connection.py`. Supabase dashboard → Project Settings → Database → Reset database password.

2. **Install deps** (Python 3.13 OK locally):

   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows / git-bash
   pip install -r requirements.txt
   ```

3. **Create `.env`** from [.env.example](.env.example). Fill in Supabase host/password, `ANTHROPIC_API_KEY`, and `INGEST_TOKEN` (a long random string). `VITE_API_URL` and `VITE_INGEST_TOKEN` are frontend-side and only needed at build time on Vercel.

4. **Create the schema.** Supabase → SQL Editor → paste and run [sql/schema.sql](sql/schema.sql). The script is idempotent — safe to re-run after pulling new migrations.

## Run

```bash
# 1. HTTP API for the frontend
uvicorn api.index:app --reload --port 8000

# 2. Frontend (separate terminal)
cd frontEnd && npm install && npm run dev
# then open the printed URL, pick an org in the sidebar, and either chat
# or click "+ Add to KB" to upload a file.

# 3. (Optional) Bulk-seed an existing folder of notes into one (org, sub) silo
set API_URL=http://127.0.0.1:8000
set INGEST_TOKEN=<your token>
python -m backend.ingest.pipeline ./vault stanford-innovations technology

# 4. MCP server (stdio) — for Claude Desktop / Cursor
python -m backend.expose_mcp
```

MCP config for Claude Desktop:

```json
{
  "stanford-eng-kb": {
    "command": "[PATH]/stanford-eng-kb/.venv/Scripts/python.exe",
    "args": ["-m", "backend.expose_mcp"],
    "cwd": "[PATH]/stanford-eng-kb"
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
   - `INGEST_TOKEN` — a long random string. Without it, `/api/ingest/upload` returns 503.
   - `FRONTEND_ORIGIN` (set after Vercel deploy, comma-separated for preview + prod URLs)
3. **Settings → Networking → Generate Domain.** Note the URL.
4. **Settings → Resources** — switch off Hobby (512 MB OOMs under torch). Pro/Trial gives 8 GB.
5. Smoke: `curl https://<railway-url>/api/health` → `{"ok":true}`.

### 2. Frontend on Vercel

[vercel.json](vercel.json) is a static build only.

1. **Import Project** → select this repo. Build settings auto-load.
2. **Environment Variables** — set:
   - `VITE_API_URL=https://<railway-url>` (no trailing slash)
   - `VITE_INGEST_TOKEN` — same value as `INGEST_TOKEN` on Railway. Bundled into the SPA; safe behind Vercel password protection only.
3. Deploy. Note the Vercel URL.
4. Back to Railway → set `FRONTEND_ORIGIN=https://<vercel-url>` and let it redeploy.
5. **Project → Deployment Protection** → enable password protection while in soft launch (no per-user auth yet).

### 3. Seed the data

Customers add content through the **+ Add to KB** flow in the UI — pick an org, pick a group, drop a file or paste text.

For one-time bulk import of an existing folder of notes, use the CLI from your laptop:

```bash
set API_URL=https://<railway-url>
set INGEST_TOKEN=<your token>
python -m backend.ingest.pipeline ./path/to/folder <org_id> <sub_id>
```

The CLI POSTs each supported file to `/api/ingest/upload` — same code path as the UI.

## Design notes

- **Chunking**: `RecursiveCharacterTextSplitter`, 500 chars / 100 overlap.
- **Embeddings**: `all-MiniLM-L6-v2` (384 dim) via `sentence-transformers`. Local, free, and good enough for small vaults. First run downloads ~90 MB of weights.
- **Dedup**: `(source, chunk_idx)` is a unique constraint; re-ingest does `ON CONFLICT DO UPDATE`. If you rename a file, delete its old rows first.
- **Hybrid search**: Reciprocal Rank Fusion over cosine-ANN (`<=>`) and Postgres FTS (`ts_rank_cd`). `K=60` from the Cormack/Clarke paper.
- **Streaming**: SSE over FastAPI `StreamingResponse`. `X-Accel-Buffering: no` disables proxy buffering.
- **Model**: Claude Opus 4.7 for answers, Haiku 4.5 for query rewrites.
- **Serverless connections**: [backend/shared/connection.py](backend/shared/connection.py) opens a fresh connection per request — correct for any serverless deploy (kept for when/if you swap to OpenAI embeddings and move backend to Vercel).
- **Read/ingest seam**: `backend/` is split so the read path and ingest path can be deployed as separate services later without rewriting code. The contract: `backend.read` and `backend.ingest` may both import from `backend.shared`, but **must not** import from each other. Entry points (`api/`, `backend.expose_mcp`, future `worker/`) are the only places that compose both halves. Splitting into a worker is then a directory copy, not a refactor.
- **Multi-tenancy**: every chunk in `documents` carries `metadata->>'org_id'` (and usually `'sub_id'`). [backend/read/retrieval.py](backend/read/retrieval.py) filters by both, so customers in different orgs never see each other's data. The chat-side request schemas in [api/index.py](api/index.py) require `org_id` — a frontend bug that omits it fails loud (422), not silent (cross-tenant leak).
- **Upload audit log**: every upload also writes a single row to `documents_raw` with the full extracted text + tenancy metadata. Lets us re-chunk later without re-uploading and gives customers a "download my data" path if asked.
- **Single ingest path**: customer uploads go straight to pgvector; there is no GitHub vault, no clone-on-Railway, no second source of truth. The bulk-upload CLI in [backend/ingest/pipeline.py](backend/ingest/pipeline.py) is a thin client that hits the same `/api/ingest/upload` endpoint — used only for one-time seeding, never by the deployed backend.
