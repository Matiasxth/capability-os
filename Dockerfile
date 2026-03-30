# ============================================================
# Stage 1: Build frontend
# ============================================================
FROM node:18-slim AS frontend

WORKDIR /build
COPY system/frontend/app/package.json system/frontend/app/package-lock.json* ./
RUN npm install --prefer-offline --no-audit
COPY system/frontend/app/ ./
# Empty VITE_API_BASE_URL → relative URLs → same-origin requests
ENV VITE_API_BASE_URL=""
RUN npm run build

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.12-slim

# System dependencies (minimal)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash capos

WORKDIR /app

# Python dependencies (core only — fast layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium (optional — failure is OK)
RUN pip install --no-cache-dir playwright 2>/dev/null \
    && python -m playwright install --with-deps chromium 2>/dev/null \
    || echo "Playwright not installed — browser features disabled"

# Source code
COPY system/ system/
COPY capability_os_master_spec.md .
COPY docker-entrypoint.py .
COPY pytest.ini .

# Built frontend from stage 1
COPY --from=frontend /build/dist system/frontend/app/dist/

# Workspace directories (will be overlaid by volumes)
RUN mkdir -p /data/workspace/system /data/workspace/artifacts/traces \
             /data/workspace/sequences /data/workspace/proposals/mcp

# Ownership
RUN chown -R capos:capos /app /data

USER capos

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    WORKSPACE_ROOT=/data/workspace \
    HOST=0.0.0.0 \
    PORT=8000 \
    WS_PORT=8001 \
    LLM_PROVIDER=ollama \
    OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    OLLAMA_MODEL=llama3.1:8b \
    ANTHROPIC_API_KEY="" \
    GEMINI_API_KEY="" \
    DEEPSEEK_API_KEY=""

EXPOSE 8000 8001

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["python", "docker-entrypoint.py"]
