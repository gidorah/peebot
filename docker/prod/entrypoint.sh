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

# Hand off to the container's CMD (gunicorn, celery worker, beat, or management command).
exec "$@"
