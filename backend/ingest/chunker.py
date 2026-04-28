"""Text chunking — single source of truth for how documents are split.

Both vault ingest (today) and AI extraction pipelines (future) call this so chunk
boundaries stay consistent across the system. Changing CHUNK_SIZE or
CHUNK_OVERLAP requires re-ingesting everything.

Pure-stdlib implementation: avoids pulling langchain-core (~20 MB) into the
Vercel function bundle. Behavior approximates langchain's
RecursiveCharacterTextSplitter for our use case (RAG over text):
chunks ≤ CHUNK_SIZE chars, ~CHUNK_OVERLAP chars duplicated between consecutive
chunks, breaks preferred at paragraph > line > sentence > word boundaries.
"""

from dataclasses import dataclass

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# Separators in priority order. We prefer paragraph breaks (preserve logical
# sections), then lines, sentences, then words; fall back to char-cut if none fit.
_SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass
class Chunk:
    source: str           # logical source path (e.g. "stanford-legal/family-law/<id>")
    chunk_idx: int        # 0-based position within the source
    content: str
    metadata: dict        # at minimum {"source", "chunk"}; callers may extend


def _greedy_split(text: str) -> list[str]:
    """Split text into pieces ≤ CHUNK_SIZE, preferring natural boundaries."""
    pieces: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + CHUNK_SIZE, n)
        # If we're not at the very end, try to back up to a natural break.
        # Search the back half of the window so we don't produce tiny chunks.
        if end < n:
            for sep in _SEPARATORS:
                idx = text.rfind(sep, pos + CHUNK_SIZE // 2, end)
                if idx > pos:
                    end = idx + len(sep)
                    break
        piece = text[pos:end].strip()
        if piece:
            pieces.append(piece)
        pos = end
    return pieces


def _with_overlap(pieces: list[str]) -> list[str]:
    """Prepend the last CHUNK_OVERLAP chars of each piece to the next."""
    if CHUNK_OVERLAP <= 0 or len(pieces) <= 1:
        return pieces
    out = [pieces[0]]
    for prev, curr in zip(pieces, pieces[1:]):
        prefix = prev[-CHUNK_OVERLAP:] if len(prev) > CHUNK_OVERLAP else prev
        out.append(prefix + curr)
    return out


def chunk_text(text: str, source: str, extra_metadata: dict | None = None) -> list[Chunk]:
    text = text.strip()
    if not text:
        return []

    base_meta = {"source": source}
    if extra_metadata:
        base_meta.update(extra_metadata)

    pieces = _with_overlap(_greedy_split(text))
    return [
        Chunk(
            source=source,
            chunk_idx=i,
            content=piece,
            metadata={**base_meta, "chunk": i},
        )
        for i, piece in enumerate(pieces)
    ]
