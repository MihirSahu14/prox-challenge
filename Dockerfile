# Single-service hosting image: FastAPI backend + Claude Agent SDK (which
# needs the Claude Code CLI, hence Node) + prebuilt frontend, sized for free
# tiers via fastembed (ONNX) instead of torch.
#
# Local dev does NOT use this — see README quick start (npm install / npm run dev).

# ---- stage 1: build the frontend ----
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: runtime ----
FROM python:3.11-slim
WORKDIR /app

# Node + Claude Code CLI (the Agent SDK's subprocess transport)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-deploy.txt backend/requirements-deploy.txt
RUN pip install --no-cache-dir -r backend/requirements-deploy.txt

COPY backend/ backend/
COPY --from=frontend /fe/dist frontend/dist

# Run as non-root: the Claude Code CLI (the Agent SDK's transport) refuses
# bypassPermissions when running as root, which kills every agent turn with
# "ProcessError: Command failed with exit code 1".
RUN useradd -m appuser
ENV EMBED_BACKEND=fastembed \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser \
    FASTEMBED_CACHE_PATH=/home/appuser/.cache/fastembed
USER appuser

# Bake the ONNX embedding model into the image (as appuser, into its own
# cache) so cold starts don't download it.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

WORKDIR /app/backend
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
