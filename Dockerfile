# syntax=docker/dockerfile:1
#
# Backend image for Railway. Bakes the MiniLM weights into the layer so the
# first request after a cold start is warm (no 90 MB HF download per redeploy).

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pre-download MiniLM weights into the HF cache (~/.cache/huggingface/hub).
# Keeps cold starts fast and removes a runtime network dependency on Hugging Face.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY api/ ./api/
COPY backend/ ./backend/

# Railway injects $PORT at runtime. Bind to 0.0.0.0 so the container is reachable.
CMD ["sh", "-c", "uvicorn api.index:app --host 0.0.0.0 --port ${PORT:-8000}"]
