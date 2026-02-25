#!/bin/bash
# ==============================================================================
# PeeBot - TimescaleDB Initialization Script (Shell Wrapper)
# ==============================================================================
# Runs automatically on FIRST container start only (Docker postgres init behaviour).
# Purpose: Enable TimescaleDB extension and create the pgbouncer_auth role.
# Note: Hypertables are created by Django migrations, not here.
#
# Required environment variables:
#   POSTGRES_USER           - PostgreSQL superuser name (set by Docker image)
#   POSTGRES_DB             - Database to initialise (set by Docker image)
#   PGBOUNCER_AUTH_PASSWORD - Plaintext password for the pgbouncer_auth role
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Fail fast if PGBOUNCER_AUTH_PASSWORD is not provided.
# There is no safe default — the role must have a real password.
# ------------------------------------------------------------------------------
if [ -z "${PGBOUNCER_AUTH_PASSWORD:-}" ]; then
    echo "FATAL: PGBOUNCER_AUTH_PASSWORD environment variable is required but not set." >&2
    echo "       Set it in the TimescaleDB service environment block in docker-compose.yml." >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# Pre-escape single quotes for safe bash-level interpolation into the heredoc.
# format() + %L below applies SQL-level quoting on top of this, giving two
# independent layers of protection against SQL injection / syntax errors.
# ------------------------------------------------------------------------------
ESCAPED_PASSWORD="${PGBOUNCER_AUTH_PASSWORD//\'/\'\'}"

echo "Running TimescaleDB initialisation script..."

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<EOSQL
    -- --------------------------------------------------------------------------
    -- PART 1: Enable TimescaleDB Extension
    -- --------------------------------------------------------------------------
    -- CASCADE automatically loads dependencies (timescaledb_toolkit, etc.)
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

    -- --------------------------------------------------------------------------
    -- PART 2: Create PgBouncer auth role
    -- --------------------------------------------------------------------------
    -- IMPORTANT: Password Synchronisation
    -- This password is sourced from the PGBOUNCER_AUTH_PASSWORD environment
    -- variable, which must match the password injected into PgBouncer's
    -- userlist.txt by docker/prod/pgbouncer/entrypoint.sh.
    --
    -- Why this role exists:
    --   PgBouncer uses auth_query to validate application users against
    --   pg_shadow.  The auth_query requires SUPERUSER to read pg_shadow.
    --   This dedicated superuser (pgbouncer_auth) performs only auth queries.
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgbouncer_auth') THEN
            EXECUTE format(
                'CREATE ROLE pgbouncer_auth WITH LOGIN SUPERUSER PASSWORD %L',
                '${ESCAPED_PASSWORD}'
            );
            RAISE NOTICE 'Created pgbouncer_auth superuser for PgBouncer authentication queries';
        ELSE
            RAISE NOTICE 'pgbouncer_auth role already exists, skipping creation';
        END IF;
    END \$\$;

    -- --------------------------------------------------------------------------
    -- PART 3: Verify Extension Loaded
    -- --------------------------------------------------------------------------
    -- Fail fast if extension did not load (prevents silent failures downstream)
    DO \$\$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
        ) THEN
            RAISE NOTICE 'TimescaleDB extension successfully installed';
        ELSE
            RAISE EXCEPTION 'TimescaleDB extension failed to install. Verify shared_preload_libraries includes timescaledb.';
        END IF;
    END \$\$;

    -- --------------------------------------------------------------------------
    -- PART 4: Log Successful Initialisation
    -- --------------------------------------------------------------------------
    -- Output appears in docker logs for troubleshooting
    SELECT format(
        'TimescaleDB version %s initialized successfully at %s',
        extversion,
        now()
    ) AS initialization_status
    FROM pg_extension
    WHERE extname = 'timescaledb';
EOSQL

echo "TimescaleDB initialisation complete."
