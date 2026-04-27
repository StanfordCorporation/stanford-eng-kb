"""Vercel entry point — FastAPI ASGI app.

Vercel's @vercel/python runtime detects the `app` export and serves it.
Every route is prefixed with /api/ because Vercel forwards the full path
(including /api) to the function.

Local dev:
    uvicorn api.index:app --reload --port 8000
"""

import json
import os

from dotenv import load_dotenv

# Load .env for local dev. On Vercel envs come from the platform — load_dotenv
# silently no-ops when there's no .env file, so this is safe to leave on.
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.read.retrieval import hybrid_search
from backend.read.claude_answer import answer, stream_answer, stream_chat

app = FastAPI(title="Stanford Eng KB API")

# Allow the deployed frontend (configurable) + any localhost port for dev.
# Set FRONTEND_ORIGIN in production to your deployed URL — comma-separated if
# you need multiple (preview + prod).
_extra = os.environ.get("FRONTEND_ORIGIN", "")
_origins = [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=20)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/ask")
def ask(req: AskRequest):
    return answer(req.query, k=req.k)


@app.post("/api/ask/stream")
def ask_stream(req: AskRequest):
    def sse():
        for event in stream_answer(req.query, k=req.k):
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
        for event in stream_chat(history, k=req.k):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/search")
def search(req: SearchRequest):
    return hybrid_search(req.query, k=req.k)
