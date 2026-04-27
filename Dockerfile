# syntax=docker/dockerfile:1
#
# Backend image for Railway. Bakes the MiniLM weights into the layer so the
# first request after a cold start is warm (no 90 MB HF download per redeploy).

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    HF_HUB_DOWNLOAD_TIMEOUT=120

WORKDIR /app

COPY requirements.txt .
# hf_transfer (Rust-based) gives faster, more reliable HF downloads during the build.
# Build-time only — no runtime impact, so kept out of requirements.txt.
RUN pip install -r requirements.txt && pip install hf_transfer

# Optional: authenticate HF downloads during the build for higher rate limits.
# Set HF_TOKEN as a regular variable on Railway (Service → Variables); this ARG
# pulls it into the build environment so the RUN below sees it.
ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}

# Pre-download MiniLM weights into the HF cache (~/.cache/huggingface/hub).
# Retries up to 3 times so a flaky HF response during the Railway build doesn't
# kill the whole deploy. snapshot_download is HF's lower-level, retry-friendly
# downloader; the SentenceTransformer call after it loads from cache (proves it).
RUN for i in 1 2 3; do \
        python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/all-MiniLM-L6-v2', max_workers=2)" \
            && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
            && exit 0; \
        echo "model download attempt $i failed, retrying in 10s..."; \
        sleep 10; \
    done; \
    exit 1

COPY api/ ./api/
COPY backend/ ./backend/

# Railway injects $PORT at runtime. Bind to 0.0.0.0 so the container is reachable.
CMD ["sh", "-c", "uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8000}"]
