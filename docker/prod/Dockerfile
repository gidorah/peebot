# ==============================================================================
# PeeBot - Production Docker Image (Multi-Stage Build)
# ==============================================================================
# Build with:
#   docker build -f docker/prod/Dockerfile -t peebot:local .
# (from repo root)
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: builder — Install Python dependencies into /opt/venv
# ------------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build dependencies: psycopg requires libpq-dev + build-essential for C extensions
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential libpq-dev; \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible dependency installation
RUN pip install --no-cache-dir uv

# Configure uv to install into /opt/venv (isolated from system Python)
ENV UV_PROJECT_ENVIRONMENT="/opt/venv"
ENV UV_COMPILE_BYTECODE=1

# Copy only lockfiles first for optimal layer caching.
# Re-runs uv sync only when pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./

# Install production dependencies only (excludes [dependency-groups.dev])
RUN uv sync --frozen --no-dev

# ------------------------------------------------------------------------------
# Stage 2: runtime — Minimal image with pre-built venv and baked source code
# ------------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"
ENV DJANGO_SETTINGS_MODULE=config.settings.production

# Runtime-only C library required by psycopg (not the build toolchain)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libpq5; \
    rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment from builder (no pip/uv needed at runtime)
COPY --from=builder /opt/venv /opt/venv

# Create a non-root user for security hardening
RUN groupadd -g 1000 python && \
    useradd -u 1000 -g python -m python

# Copy application source code into workspace
WORKDIR /workspace
COPY . /workspace/

# Transfer workspace ownership to the non-root user
RUN chown -R python:python /workspace

# Copy entrypoint script to /usr/local/bin so it is never shadowed by volume mounts.
# chmod must run as root (before USER directive).
COPY docker/prod/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Drop privileges — all subsequent runtime processes run as non-root
USER python

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Default command: Gunicorn WSGI server.
# Override this in docker-compose.yml for worker/beat/ingestion services.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
