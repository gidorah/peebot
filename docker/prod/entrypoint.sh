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

# Collect static files so WhiteNoise can serve them.
# Only needed for the web (gunicorn) service — skip for worker, beat, and ingestion.
if [ "$1" = "gunicorn" ]; then
    echo "Running collectstatic..."
    python manage.py collectstatic --noinput
fi

# Hand off to the container's CMD (gunicorn, celery worker, beat, or management command).
exec "$@"
