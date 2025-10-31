-- ==============================================================================
-- PeeBot - TimescaleDB Initialization Script
-- ==============================================================================
-- Runs automatically on FIRST container start only (Docker postgres init behavior).
-- Purpose: Enable TimescaleDB extension before Django migrations run.
-- Note: Hypertables are created by Django migrations, not here.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- PART 1: Enable TimescaleDB Extension
-- ------------------------------------------------------------------------------
-- CASCADE automatically loads dependencies (timescaledb_toolkit, etc.)
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ------------------------------------------------------------------------------
-- PART 1B: Ensure PgBouncer auth user exists (SCRAM password matches userlist)
-- ------------------------------------------------------------------------------
-- ⚠️  CRITICAL: Password Synchronization Required
-- This password MUST match in THREE locations:
--   1. docker/dev/pgbouncer/userlist.txt (as SCRAM-SHA-256 hash)
--   2. .env file (PGBOUNCER_AUTH_PASSWORD variable)
--   3. This SQL file (hardcoded below)
--
-- To update the password:
--   1. Change password in this file
--   2. Update PGBOUNCER_AUTH_PASSWORD in .env
--   3. Run: docker/dev/pgbouncer/generate_userlist.sh pgbouncer_auth <new_password>
--   4. Update docker/dev/pgbouncer/userlist.txt with the generated hash
--   5. Rebuild containers: just dev-down && just dev-up
--
-- Why this user exists:
--   PgBouncer uses auth_query to validate application users against pg_shadow.
--   The auth_query requires SUPERUSER privileges to read pg_shadow table.
--   This dedicated superuser (pgbouncer_auth) performs only authentication queries.
-- ------------------------------------------------------------------------------
DO $pgbouncer_init$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'pgbouncer_auth'
    ) THEN
        -- Superuser privileges required for auth_query to read pg_shadow
        EXECUTE $sql$CREATE ROLE pgbouncer_auth WITH LOGIN SUPERUSER PASSWORD 'pgbouncer_auth_password'$sql$;
        RAISE NOTICE 'Created pgbouncer_auth superuser for PgBouncer authentication queries';
    ELSE
        RAISE NOTICE 'pgbouncer_auth role already exists, skipping creation';
    END IF;
END $pgbouncer_init$;

-- ------------------------------------------------------------------------------
-- PART 2: Verify Installation
-- ------------------------------------------------------------------------------
-- Fail fast if extension didn't load (prevents silent failures downstream)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
    ) THEN
        RAISE NOTICE 'TimescaleDB extension successfully installed';
    ELSE
        RAISE EXCEPTION 'TimescaleDB extension failed to install. Verify shared_preload_libraries includes timescaledb.';
    END IF;
END $$;

-- ------------------------------------------------------------------------------
-- PART 3: Log Successful Initialization
-- ------------------------------------------------------------------------------
-- Output appears in `docker logs peebot_timescaledb_dev` for troubleshooting
SELECT format(
    'TimescaleDB version %s initialized successfully at %s',
    extversion,
    now()
) AS initialization_status
FROM pg_extension
WHERE extname = 'timescaledb';
