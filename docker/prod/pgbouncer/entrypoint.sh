#!/bin/sh
# ==============================================================================
# PgBouncer Entrypoint - Production
# ==============================================================================
# Generates /etc/pgbouncer/userlist.txt at container start from the
# PGBOUNCER_AUTH_PASSWORD environment variable, then hands off to pgbouncer.
#
# WHY: The production userlist.txt is gitignored. Coolify clones the repo fresh
# on every deploy, so the file will never be present on disk. Generating it at
# runtime from a Coolify-injected env var is the only Coolify-compatible
# approach that keeps secrets out of version control entirely.
# ==============================================================================
set -euo pipefail

# Fail fast with a clear message if the required env var is missing.
if [ -z "${PGBOUNCER_AUTH_PASSWORD:-}" ]; then
    echo "FATAL: PGBOUNCER_AUTH_PASSWORD environment variable is required" >&2
    echo "Set it in the Coolify environment variable configuration." >&2
    exit 1
fi

# Generate userlist.txt with the plaintext password.
# PgBouncer requires a plaintext password in userlist.txt when using auth_query
# mode: it needs the plaintext credential to complete SCRAM-SHA-256
# challenge-response with PostgreSQL on behalf of the connecting client.
# See: https://www.pgbouncer.org/config.html#auth_file
# Write with umask 177 so the file is created at mode 0600 atomically;
# no subsequent chmod is needed and there is no window of world-readability.
(umask 177; echo "\"pgbouncer_auth\" \"${PGBOUNCER_AUTH_PASSWORD}\"" > /etc/pgbouncer/userlist.txt)

echo "Generated /etc/pgbouncer/userlist.txt for pgbouncer_auth user"

# Hand off to pgbouncer, passing through all arguments (the config file path).
exec pgbouncer "$@"
