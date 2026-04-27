"""Answer a question against the knowledge base using Claude + retrieved context."""

import sys

from anthropic import Anthropic

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .retrieval import hybrid_search

client = Anthropic()

MODEL = "claude-opus-4-7"
REWRITE_MODEL = "claude-haiku-4-5"


REWRITE_SYSTEM = """You rewrite the latest user message into a standalone search query \
for retrieving passages from a knowledge base (hybrid vector + keyword search). Resolve \
pronouns and implied subjects from prior turns so the query stands alone.

Rules:
- Output ONLY the rewritten query. No prose, no preamble, no quotes, no trailing punctuation.
- One line. Keep concrete nouns from the original question.
- If the latest message is already a well-formed standalone question, echo it verbatim."""


def rewrite_query(messages: list[dict]) -> str:
    """Use a small model to turn the latest user turn into a standalone search query.
    No-op for the first turn (nothing to disambiguate from)."""
    if len(messages) <= 1:
        return messages[-1]["content"]

    history = "\n".join(
        f"{m['role'].capitalize()}: {m['content']}" for m in messages
    )
    try:
        res = client.messages.create(
            model=REWRITE_MODEL,
            max_tokens=200,
            system=REWRITE_SYSTEM,
            messages=[{"role": "user", "content": history}],
        )
        rewritten = res.content[0].text.strip().strip('"').strip()
        return rewritten or messages[-1]["content"]
    except Exception:
        # Never fail the request on a rewrite error — fall back to the raw latest turn.
        return messages[-1]["content"]


def _build_prompt(hits, query):
    context = "\n\n".join(
        f"[{i+1}] source={h['metadata'].get('source')}\n{h['content']}"
        for i, h in enumerate(hits)
    )
    return f"""Answer the question using ONLY the context below. Cite sources inline
using the [n] numbers. If the answer is not in the context, say so.

Context:
{context}

Question: {query}
"""


def _sources(hits):
    return [
        {"n": i + 1, "source": h["metadata"].get("source"), "score": h["score"]}
        for i, h in enumerate(hits)
    ]


def answer(query: str, k: int = 5) -> dict:
    hits = hybrid_search(query, k=k)
    res = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": _build_prompt(hits, query)}],
    )
    return {"answer": res.content[0].text, "sources": _sources(hits)}


def stream_answer(query: str, k: int = 5):
    """Generator of event dicts: sources (once), delta (many), done (once)."""
    hits = hybrid_search(query, k=k)
    yield {"type": "sources", "sources": _sources(hits)}

    with client.messages.stream(
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": _build_prompt(hits, query)}],
    ) as stream:
        for text in stream.text_stream:
            yield {"type": "delta", "text": text}

    yield {"type": "done"}


CHAT_SYSTEM = """You are a knowledge-base assistant answering questions about the user's \
Obsidian vault. For the LATEST user question, answer using ONLY the context provided \
below. Cite sources inline using [n] numbers matching the context. If the answer is not \
in the context, say so. Use prior conversation turns only for pronoun resolution and \
follow-up intent — do not invent facts from them.

Context for the latest question:
{context}"""


def stream_chat(messages: list[dict], k: int = 5):
    """Multi-turn chat. `messages` follows Anthropic's format; last role must be 'user'.
    Retrieval runs fresh against the latest user turn each call."""
    if not messages or messages[-1].get("role") != "user":
        raise ValueError("messages must be non-empty and end with a user turn")

    latest = messages[-1]["content"]
    search_query = rewrite_query(messages)
    hits = hybrid_search(search_query, k=k)
    yield {
        "type": "sources",
        "sources": _sources(hits),
        "rewritten_query": search_query if search_query != latest else None,
    }

    context = "\n\n".join(
        f"[{i+1}] source={h['metadata'].get('source')}\n{h['content']}"
        for i, h in enumerate(hits)
    )
    system = CHAT_SYSTEM.format(context=context)

    with client.messages.stream(
        model=MODEL,
        max_tokens=1000,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield {"type": "delta", "text": text}

    yield {"type": "done"}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Summarise this vault."
    result = answer(q)
    print(result["answer"])
    print("\nSources:")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['source']} (score={s['score']:.4f})")
