# ═══════════════════════════════════════════════════════════
# NeuroShell v5 — AI-Powered Intelligent Terminal
# Multi-stage Docker build with C++ engine compilation
# ═══════════════════════════════════════════════════════════

FROM python:3.12-slim AS base

# Metadata
LABEL maintainer="Abneesh Singh <singhabneesh250@gmail.com>"
LABEL description="NeuroShell v5 — AI-Powered Intelligent Terminal with C++ Engine"
LABEL version="5.0.0"

WORKDIR /app

# System deps for building C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl git && \
    rm -rf /var/lib/apt/lists/*

# ── Stage 1: Install Python dependencies ──
FROM base AS deps
COPY requirements.txt .
COPY setup.py .
COPY cpp_engine/ cpp_engine/
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pybind11>=2.11 ollama>=0.3 groq>=0.4 && \
    python setup.py build_ext --inplace || echo 'C++ build skipped (using Python fallback)'

# ── Stage 2: Production image ──
FROM python:3.12-slim AS production

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Install runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git && \
    rm -rf /var/lib/apt/lists/*

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data /app/data/models /app/data/history

# Environment
ENV NEUROSHELL_DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1
ENV TERM=xterm-256color

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "from config import Config; Config.load()" || exit 1

# Entry point — CLI mode (Desktop GUI not available in Docker)
ENTRYPOINT ["python", "main.py"]
