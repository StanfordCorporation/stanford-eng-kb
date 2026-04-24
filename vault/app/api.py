"""FastAPI server exposing the knowledge base over HTTP.

Run:  uvicorn api:app --reload --port 8000
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from retrieval import hybrid_search
from claude_answer import answer, stream_answer, stream_chat

app = FastAPI(title="Stanford Eng KB API")

# Dev-only: allow the Vite dev server. Tighten before any non-localhost use.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST", "GET"],
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


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
def ask(req: AskRequest):
    return answer(req.query, k=req.k)


@app.post("/ask/stream")
def ask_stream(req: AskRequest):
    def sse():
        for event in stream_answer(req.query, k=req.k):
            yield f"data: {json.dumps(event)}\n\n"

    # Disable buffering at proxies so chunks flush immediately.
    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/stream")
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


@app.post("/search")
def search(req: SearchRequest):
    return hybrid_search(req.query, k=req.k)
