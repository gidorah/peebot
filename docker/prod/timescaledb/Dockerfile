# ==============================================================================
# PeeBot - TimescaleDB Production Image
# ==============================================================================
# Extends the upstream TimescaleDB image to bake in the init script.
# This avoids bind mounts, which are unreliable in Coolify deployments
# (the cloned repo may not persist on the host at the expected path).
#
# Build context must be the repo root so the COPY can reach docker/scripts/.
#
# The init script runs ONLY on first container start (standard PostgreSQL
# entrypoint behaviour) — it creates the TimescaleDB extension and the
# pgbouncer_auth role.
# ==============================================================================
FROM timescale/timescaledb:latest-pg15

COPY docker/scripts/init-timescale.sh /docker-entrypoint-initdb.d/01-init-timescale.sh
RUN chmod +x /docker-entrypoint-initdb.d/01-init-timescale.sh
