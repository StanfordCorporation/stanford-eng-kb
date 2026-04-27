"""Pluggable source for raw documents to ingest.

Today: LocalVaultLoader walks a directory of *.md files.
Future: GitVaultLoader pulls a private repo; S3VaultLoader reads object storage.

The pipeline takes a VaultLoader; it does not know about disks or git. To add a
new source, implement `iter_documents()` returning `RawDoc` instances.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol


@dataclass
class RawDoc:
    source: str   # logical relative path, forward-slashed (stable across hosts)
    text: str


class VaultLoader(Protocol):
    def iter_documents(self) -> Iterable[RawDoc]: ...


class LocalVaultLoader:
    """Walks *.md files under a local directory."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def iter_documents(self) -> Iterable[RawDoc]:
        for path in self.root.rglob("*.md"):
            rel = str(path.relative_to(self.root)).replace("\\", "/")
            yield RawDoc(source=rel, text=path.read_text(encoding="utf-8"))
