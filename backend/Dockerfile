# syntax=docker/dockerfile:1
# ==============================================================================
# Multi-Stage Optimized Production Dockerfile for Schwarz Research Intelligence
# Produces a secure, minimal non-root image with precompiled binary wheels.
# ==============================================================================

# Stage 1: Build Dependencies & Python Wheels
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install build-time compilers and native libraries with cache mounts
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Minimal Runtime Container
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.12/site-packages:/app:$PYTHONPATH"

WORKDIR /app

# Install minimal runtime dependencies (libpq5, poppler-utils for PDF rendering, curl for healthchecks)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /install /install

# Copy application source code
COPY . /app/

# Create non-root system user & set permissions
RUN addgroup --system --gid 10001 appgroup && \
    adduser --system --uid 10001 --ingroup appgroup --home /app appuser && \
    chmod +x /app/entrypoint.sh && \
    mkdir -p /app/staticfiles /app/media /app/cache /app/workspaces && \
    chown -R appuser:appgroup /app /install

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || curl -f http://localhost:8001/sse || pgrep -f "celery" > /dev/null || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
