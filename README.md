# Stanford KB

Multi-tenant RAG: customers upload `.md`/`.txt`/`.pdf`/`.docx` files (or paste text)
into an org/sub-org silo, and chat against their own slice of the knowledge base.

```
 file or text upload (per org)  ──►  extract → chunk → embed (OpenAI)
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
├── .vercelignore
├── api/
│   └── index.py              # FastAPI ASGI app (Vercel function in prod, uvicorn in dev)
├── backend/                  # Python library, split into read / ingest / shared
│   ├── shared/
│   │   ├── connection.py     # psycopg2 + pgvector, per-request connections
│   │   └── embedder.py       # OpenAI text-embedding-3-small (384 dim) — query AND doc
│   ├── read/                 # query path
│   │   ├── retrieval.py      # hybrid search w/ RRF
│   │   └── claude_answer.py  # Claude grounded Q&A, streaming
│   ├── ingest/               # write path (one upload at a time)
│   │   ├── chunker.py        # single source of truth for chunk boundaries
│   │   ├── extractors.py     # md/txt/pdf/docx → plain text
│   │   ├── uploads.py        # one upload → documents_raw + documents (with org metadata)
│   │   └── pipeline.py       # bulk-upload CLI (client; POSTs to /api/ingest/upload)
│   └── expose_mcp.py         # FastMCP server (read-only)
├── frontEnd/                 # React/Vite SPA
├── sql/schema.sql            # run once in Supabase SQL Editor
├── requirements.txt
└── vercel.json               # Vercel build + Python function config
```

## Setup

1. **Rotate the Supabase DB password.** The old one was committed into `connection.py`. Supabase dashboard → Project Settings → Database → Reset database password.

2. **Install deps** (Python 3.13 OK locally):

   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows / git-bash
   pip install -r requirements.txt
   ```

3. **Create `.env`** from [.env.example](.env.example). Fill in Supabase host/password, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and `INGEST_TOKEN` (a long random string). `VITE_INGEST_TOKEN` is frontend-side and only needed at build time on Vercel.

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

Single-platform: **Vercel** (frontend + Python serverless function) → **Supabase** (pgvector).

Embeddings via OpenAI; chat answers via Anthropic Claude. The Python backend fits Vercel's 250 MB function limit because `sentence-transformers`/`torch` are gone.

### 1. Vercel — frontend + backend

[vercel.json](vercel.json) registers `api/index.py` as a Python function with `backend/**` included. Same-origin routing means the SPA hits `/api/*` directly with no CORS dance.

1. **Import Project** → select this repo. Build settings auto-load.
2. **Environment Variables** — set:
   - `SUPABASE_DB_HOST` (use the **pooler** endpoint, e.g. `aws-0-<region>.pooler.supabase.com`)
   - `SUPABASE_DB_PORT=6543`
   - `SUPABASE_DB_NAME=postgres`
   - `SUPABASE_DB_USER=postgres.<project-ref>`
   - `SUPABASE_DB_PASSWORD`
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `INGEST_TOKEN` — a long random string. Without it, `/api/ingest/upload` returns 503.
   - `VITE_INGEST_TOKEN` — **same value** as `INGEST_TOKEN`. Bundled into the SPA so the upload form can send it. Safe behind Vercel password protection only.
3. Deploy. The build runs `npm ci && npm run build` for the SPA and bundles the Python function from `requirements.txt` automatically.
4. Smoke test: `curl https://<your-app>.vercel.app/api/health` → `{"ok":true}`.
5. **Project → Deployment Protection** → enable password protection while in soft launch (no per-user auth yet).

### 2. Seed the data

Customers add content through the **+ Add to KB** flow in the UI — pick an org, pick a group, drop a file or paste text.

For one-time bulk import of an existing folder of notes, use the CLI from your laptop:

```bash
set API_URL=https://<your-app>.vercel.app
set INGEST_TOKEN=<your token>
python -m backend.ingest.pipeline ./path/to/folder <org_id> <sub_id>
```

The CLI POSTs each supported file to `/api/ingest/upload` — same code path as the UI.

## Design notes

- **Chunking**: `RecursiveCharacterTextSplitter`, 500 chars / 100 overlap.
- **Embeddings**: OpenAI `text-embedding-3-small`, requested at 384 dim (Matryoshka truncation) so the existing `vector(384)` column and HNSW index don't need migration. ~$0.02 per million tokens — pennies/month at this scale.
- **Dedup**: `(source, chunk_idx)` is a unique constraint; re-ingest does `ON CONFLICT DO UPDATE`. If you rename a file, delete its old rows first.
- **Hybrid search**: Reciprocal Rank Fusion over cosine-ANN (`<=>`) and Postgres FTS (`ts_rank_cd`). `K=60` from the Cormack/Clarke paper.
- **Streaming**: SSE over FastAPI `StreamingResponse`. `X-Accel-Buffering: no` disables proxy buffering.
- **Model**: Claude Opus 4.7 for answers, Haiku 4.5 for query rewrites.
- **Serverless connections**: [backend/shared/connection.py](backend/shared/connection.py) opens a fresh connection per request — required on Vercel where each invocation is a fresh container. The Supabase **pooler** (port 6543) is what makes this affordable.
- **Read/ingest seam**: `backend/` is split so the read path and ingest path can be deployed as separate services later without rewriting code. The contract: `backend.read` and `backend.ingest` may both import from `backend.shared`, but **must not** import from each other. Entry points (`api/`, `backend.expose_mcp`, future `worker/`) are the only places that compose both halves. Splitting into a worker is then a directory copy, not a refactor.
- **Multi-tenancy**: every chunk in `documents` carries `metadata->>'org_id'` (and usually `'sub_id'`). [backend/read/retrieval.py](backend/read/retrieval.py) filters by both, so customers in different orgs never see each other's data. The chat-side request schemas in [api/index.py](api/index.py) require `org_id` — a frontend bug that omits it fails loud (422), not silent (cross-tenant leak).
- **Shared content**: rows tagged `metadata->>'org_id' = '_shared'` (the `SHARED_ORG_ID` sentinel) bypass the tenant filter and appear in every customer's chat. The "+ Add to KB" UI can only write to a real org; only the operator can put rows in the shared bucket via the bulk CLI: `python -m backend.ingest.pipeline ./folder _shared _shared`. Use sparingly — anything in the shared bucket is visible to every tenant.
- **Upload audit log**: every upload also writes a single row to `documents_raw` with the full extracted text + tenancy metadata. Lets us re-chunk later without re-uploading and gives customers a "download my data" path if asked.
- **Single ingest path**: customer uploads go straight to pgvector; there is no GitHub vault, no clone-on-Railway, no second source of truth. The bulk-upload CLI in [backend/ingest/pipeline.py](backend/ingest/pipeline.py) is a thin client that hits the same `/api/ingest/upload` endpoint — used only for one-time seeding, never by the deployed backend.
