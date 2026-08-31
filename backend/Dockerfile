# syntax=docker/dockerfile:1
# ==============================================================================
# Fast & Lightweight Production Dockerfile for Schwarz Research Intelligence
# Uses virtualenv in /opt/venv and native --chown for instant layer builds.
# ==============================================================================

# Stage 1: Build Dependencies in /opt/venv
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install compilation headers
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install packages
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Minimal Runtime Container
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install minimal runtime libraries (PostgreSQL client, Poppler for PDF rendering, curl, procps for healthchecks)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    poppler-utils \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first so COPY --chown sets ownership instantly without slow chown -R
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -d /app -s /bin/sh appuser && \
    mkdir -p /app/staticfiles /app/media /app/cache /app/workspaces && \
    chown -R appuser:appgroup /app

# Copy virtual environment and source code with direct ownership
COPY --chown=appuser:appgroup --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup . /app/

RUN chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000 8001

ENTRYPOINT ["/app/entrypoint.sh"]
