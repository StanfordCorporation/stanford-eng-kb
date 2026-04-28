"""One-shot bulk-upload CLI for seeding a folder of files into a single
(org, sub) silo. Hits the live /api/ingest/upload endpoint — the same path
customers use — so there is no privileged direct-DB ingest in the system.

NOT used by the deployed backend. Run from your laptop after the API is up:

    set API_URL=https://<railway-url>          # or http://127.0.0.1:8000 for local
    set INGEST_TOKEN=<your token>
    python -m backend.ingest.pipeline ./path/to/folder stanford-innovations technology

Walks the folder recursively, uploads every supported file, prints a summary.
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from .extractors import SUPPORTED_EXTENSIONS

# Read .env from the project root so API_URL / INGEST_TOKEN don't have to be
# set in the shell — match the rest of the project's entry points.
load_dotenv()


def main(folder: str, org_id: str, sub_id: str) -> None:
    api_url = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.environ.get("INGEST_TOKEN")
    if not token:
        sys.exit("INGEST_TOKEN env var is required")

    root = Path(folder)
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")

    endpoint = f"{api_url}/api/ingest/upload"
    headers = {"X-Ingest-Token": token}

    files = sorted(
        p
        for ext in SUPPORTED_EXTENSIONS
        for p in root.rglob(f"*{ext}")
    )
    if not files:
        sys.exit(f"no supported files under {root}")

    print(f"Uploading {len(files)} files → {endpoint}")
    succeeded = 0
    failed: list[tuple[Path, str]] = []

    with httpx.Client(timeout=120) as client:
        for path in files:
            rel = path.relative_to(root)
            with path.open("rb") as fh:
                resp = client.post(
                    endpoint,
                    headers=headers,
                    data={"org_id": org_id, "sub_id": sub_id},
                    files={"file": (path.name, fh, "application/octet-stream")},
                )
            if resp.is_success:
                data = resp.json()
                print(f"  ok  {rel}  ({data['chunks']} chunks)")
                succeeded += 1
            else:
                print(f"  err {rel}  ({resp.status_code} {resp.text})")
                failed.append((rel, resp.text))

    print(f"\nDone: {succeeded} ok, {len(failed)} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: python -m backend.ingest.pipeline <folder> <org_id> <sub_id>")
    main(sys.argv[1], sys.argv[2], sys.argv[3])
