#!/bin/bash
# ==============================================================================
# PeeBot - Production Container Entrypoint
# ==============================================================================
# Runs at container start before the main CMD process.
# Placed at /usr/local/bin/entrypoint.sh (not inside /workspace) so it is
# never shadowed by volume mounts, per AGENTS.md entrypoint policy.
#
# Usage:
#   ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
#   CMD        ["gunicorn", ...]   # or celery, python manage.py, etc.
# ==============================================================================

set -e

# Static files are pre-collected at Docker build time (see Dockerfile).
# No runtime collectstatic needed — WhiteNoise serves the baked-in files.

# Run database migrations before the web server starts.
# Only the gunicorn (web) service runs this — worker, beat, and ingestion
# depend on pgbouncer health but skip migrations to avoid race conditions.
# `migrate` is idempotent: already-applied migrations are skipped.
if [ "$1" = "gunicorn" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput

    echo "Seeding telemetry channels..."
    python manage.py seed_channels
fi

# Wait for PgBouncer to be reachable before starting any service that queries
# the database (celery worker, beat, or ingestion).
# `depends_on: condition: service_healthy` handles initial startup ordering,
# but Docker's `restart: unless-stopped` policy restarts containers without
# re-evaluating depends_on, so this loop guards against the DNS / TCP
# unavailability window during container restarts.
if [ "$1" = "celery" ] || [ "$1" = "python" ]; then
    echo "Waiting for PgBouncer to be ready..."
    python - <<'EOF'
import sys, time, socket

host = "pgbouncer"
port = 6432
deadline = time.monotonic() + 60

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("PgBouncer is ready.")
            sys.exit(0)
    except OSError as exc:
        if time.monotonic() >= deadline:
            print(f"PgBouncer not available after 60 s: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"PgBouncer not ready yet ({exc}). Retrying in 2 s...")
        time.sleep(2)
EOF
fi

# Wait for Redis to be reachable before starting Celery worker or beat.
# Same rationale as the PgBouncer check above — the Celery consumer needs a
# live broker before its first connection attempt.
if [ "$1" = "celery" ]; then
    echo "Waiting for Redis to be ready..."
    python - <<'EOF'
import os, sys, time
import redis as redis_lib

url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
deadline = time.monotonic() + 60

while True:
    try:
        client = redis_lib.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        client.close()
        print("Redis is ready.")
        sys.exit(0)
    except Exception as exc:
        if time.monotonic() >= deadline:
            print(f"Redis not available after 60 s: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Redis not ready yet ({exc}). Retrying in 2 s...")
        time.sleep(2)
EOF
fi

# Hand off to the container's CMD (gunicorn, celery worker, beat, or management command).
exec "$@"
