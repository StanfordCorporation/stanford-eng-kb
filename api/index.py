"""HTTP entry point — FastAPI ASGI app. Routes are /api/*; we keep that prefix
on Railway so the frontend can hit the same paths in dev (Vite proxy) and prod.

Local dev:
    uvicorn api.index:app --reload --port 8000
"""

import json
import os

from dotenv import load_dotenv

# Load .env for local dev. On Railway/Vercel, env vars come from the platform —
# load_dotenv silently no-ops when there's no .env file.
load_dotenv()

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.read.retrieval import hybrid_search
from backend.read.claude_answer import answer, stream_answer, stream_chat
from backend.ingest.extractors import SUPPORTED_EXTENSIONS, UnsupportedFileType
from backend.ingest.uploads import ingest_upload

app = FastAPI(title="Stanford KB API")

# Allow the deployed frontend (configurable) + any localhost port for dev.
# FRONTEND_ORIGIN may be comma-separated (preview + prod URLs).
_extra = os.environ.get("FRONTEND_ORIGIN", "")
_origins = [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Auth ────────────────────────────────────────────────────────────────────
INGEST_TOKEN = os.environ.get("INGEST_TOKEN")


def _require_ingest_token(token: str | None) -> None:
    if not INGEST_TOKEN:
        # Misconfiguration: fail closed rather than silently allow everyone.
        raise HTTPException(status_code=503, detail="ingest disabled (INGEST_TOKEN not set)")
    if not token or token != INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing ingest token")


# ─── Request schemas (read path) ─────────────────────────────────────────────
class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)
    org_id: str = Field(min_length=1)
    sub_id: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)
    org_id: str = Field(min_length=1)
    sub_id: str | None = None


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)
    org_id: str = Field(min_length=1)
    sub_id: str | None = None


# ─── Routes (read path) ──────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/ask")
def ask(req: AskRequest):
    return answer(req.query, k=req.k, org_id=req.org_id, sub_id=req.sub_id)


@app.post("/api/ask/stream")
def ask_stream(req: AskRequest):
    def sse():
        for event in stream_answer(req.query, k=req.k, org_id=req.org_id, sub_id=req.sub_id):
            yield f"data: {json.dumps(event)}\n\n"

    # X-Accel-Buffering=no disables proxy buffering so chunks flush immediately.
    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    history = [m.model_dump() for m in req.messages]

    def sse():
        for event in stream_chat(history, k=req.k, org_id=req.org_id, sub_id=req.sub_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/search")
def search(req: SearchRequest):
    return hybrid_search(req.query, k=req.k, org_id=req.org_id, sub_id=req.sub_id)


# ─── Routes (write path) ─────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — bump if customers need bigger.


@app.post("/api/ingest/upload")
async def ingest_upload_route(
    org_id: str = Form(...),
    sub_id: str = Form(...),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    x_ingest_token: str | None = Header(None),
):
    _require_ingest_token(x_ingest_token)

    has_file = file is not None and bool(file.filename)
    has_text = text is not None and bool(text.strip())
    if has_file == has_text:
        raise HTTPException(status_code=400, detail="provide exactly one of: file, text")

    try:
        if has_file:
            data = await file.read()  # type: ignore[union-attr]
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"file exceeds {MAX_UPLOAD_BYTES} bytes",
                )
            return ingest_upload(
                org_id=org_id,
                sub_id=sub_id,
                file_name=file.filename,  # type: ignore[union-attr]
                file_bytes=data,
            )
        return ingest_upload(org_id=org_id, sub_id=sub_id, text=text)
    except UnsupportedFileType as e:
        raise HTTPException(
            status_code=415,
            detail=f"{e}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
