# I.S.C. Helwigii — Cuneiform Analysis Platform
# Classical Frontispiece Edition v2.0.0
# Multi-stage build for minimal production image

# ──────────────────────────────────────────────
# BASE STAGE — Common dependencies
# ──────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies for opencv, FAISS, and scientific stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libxcb1 libgl1 \
    libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ──────────────────────────────────────────────
# BUILD STAGE — Install Python dependencies
# ──────────────────────────────────────────────
FROM base AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better cache
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt

# ──────────────────────────────────────────────
# RUNTIME STAGE — Minimal production image
# ──────────────────────────────────────────────
FROM base AS runtime

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /bin/bash appuser

# Create data directories
RUN mkdir -p /data /data/prebaked_embeddings /data/export /data/images \
    && chown -R appuser:appuser /app /data

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default command
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]