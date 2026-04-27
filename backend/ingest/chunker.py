"""Text chunking — single source of truth for how documents are split.

Both vault ingest (today) and AI extraction pipelines (future) call this so chunk
boundaries stay consistent across the system. Changing CHUNK_SIZE or CHUNK_OVERLAP
requires re-ingesting everything.
"""

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)


@dataclass
class Chunk:
    source: str           # logical source path (e.g. "notes/inbox/foo.md")
    chunk_idx: int        # 0-based position within the source
    content: str
    metadata: dict        # at minimum {"source", "chunk"}; callers may extend


def chunk_text(text: str, source: str, extra_metadata: dict | None = None) -> list[Chunk]:
    base_meta = {"source": source}
    if extra_metadata:
        base_meta.update(extra_metadata)

    return [
        Chunk(
            source=source,
            chunk_idx=i,
            content=piece,
            metadata={**base_meta, "chunk": i},
        )
        for i, piece in enumerate(_splitter.split_text(text))
    ]
