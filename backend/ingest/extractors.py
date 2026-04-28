"""Turn an uploaded blob into plain text we can chunk.

Single source of truth for "how do we read each file type." Adding a new
extension means adding a branch here; no other ingest code needs to know.

Supported today:
- .md, .txt   UTF-8 decode
- .pdf        pypdf
- .docx       python-docx
"""

from io import BytesIO
from pathlib import PurePath

SUPPORTED_EXTENSIONS = (".md", ".txt", ".pdf", ".docx")


class UnsupportedFileType(ValueError):
    """Raised when an upload has an extension we don't know how to read."""


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext in (".md", ".txt"):
        return data.decode("utf-8", errors="replace").strip()
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext == ".docx":
        return _extract_docx(data)
    raise UnsupportedFileType(f"Unsupported file type: {ext or '(none)'}")


def _extract_pdf(data: bytes) -> str:
    # Lazy import — keeps the module light when only md/txt is in use.
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _extract_docx(data: bytes) -> str:
    # docx2txt is a ~10 KB pure-Python lib. We use it instead of python-docx
    # to avoid pulling lxml (~30 MB unzipped) into the Vercel function bundle.
    import docx2txt

    return (docx2txt.process(BytesIO(data)) or "").strip()
