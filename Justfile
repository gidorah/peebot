# Development automation recipes for PeeBot
set shell := ["bash", "-c"]
set dotenv-load := true

dev-compose := "docker compose -f docker/dev/docker-compose.yml"
prod-compose := "docker compose --project-directory . -f docker/prod/docker-compose.yml"

# Show available recipes
default:
	@just --list

# Start development stack with optional service subset (default: all)
dev-up *services:
	if [ "{{services}}" = "" ]; then {{dev-compose}} up --build -d; else {{dev-compose}} up --build -d {{services}}; fi

# Stop and remove development containers
dev-down:
	{{dev-compose}} down --remove-orphans

# Stop containers but keep them around
dev-stop:
	{{dev-compose}} stop

# Tail logs for a specific service (default: web)
dev-logs service="web":
	{{dev-compose}} logs -f {{service}}

# Open an interactive shell inside a service container (default: web)
dev-shell service="web":
	{{dev-compose}} exec {{service}} /bin/bash

# Open the Django shell
dev-django-shell:
	{{dev-compose}} exec web uv run python manage.py shell

# Run a Python script or command inside the web container
dev-python *args:
	{{dev-compose}} run --rm web uv run python {{args}}

# Apply database migrations via the web container (through PgBouncer)
# WARNING: PgBouncer enforces query_timeout=30s. Use dev-migrate-direct for
# heavy migrations (bulk DML, index builds, TimescaleDB decompression).
dev-migrate:
	{{dev-compose}} run --rm web uv run python manage.py migrate

# Apply migrations bypassing PgBouncer (direct TimescaleDB on port 5432)
# Use this for: bulk-DML migrations, index builds, TimescaleDB decompression ops,
# or any migration that takes >30 seconds.
dev-migrate-direct:
	{{dev-compose}} run --rm \
		-e DATABASE_URL="postgresql://${POSTGRES_USER:-peebot_user}:${POSTGRES_PASSWORD:-password}@timescaledb:5432/${POSTGRES_DB:-peebot}?application_name=django-migrate" \
		web uv run python manage.py migrate

# Create a Django superuser through the web container
dev-createsuperuser:
	{{dev-compose}} run --rm web uv run python manage.py createsuperuser

# Run pytest suite in Docker (accepts additional args)
dev-test *args:
	{{dev-compose}} run --rm web uv run pytest {{args}}

# Run pytest suite locally (direct DB connection for test DB creation)
# Uses direct TimescaleDB connection because:
# 1. pytest-django needs to CREATE/DROP test_peebot database
# 2. PgBouncer can't route to non-existent databases
# 3. This matches production practice where migrations also bypass PgBouncer
test *args:
	DOTENV_PATH="${DOTENV_PATH:-.env.local}" uv run pytest {{args}}

# Run linting locally
lint:
	uv run ruff check .

# Run linting and type checks inside the web container
dev-check:
	{{dev-compose}} run --rm web uv run ruff check .
	{{dev-compose}} run --rm web uv run mypy apps/

# Quickly access TimescaleDB directly using psql
dev-psql:
	psql "${TIMESCALE_DIRECT_URL:-postgresql://${POSTGRES_USER:-peebot_user}:${POSTGRES_PASSWORD:-password}@localhost:5432/${POSTGRES_DB:-peebot}}"

# Show PgBouncer pool statistics (quick view)
dev-pgbouncer:
	psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}" -c "SHOW POOLS;"

# Show detailed PgBouncer statistics (pools, stats, servers, clients)
dev-pgbouncer-stats:
	@echo "=== Pool Status ==="
	@psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}" -c "SHOW POOLS;"
	@echo ""
	@echo "=== Performance Statistics ==="
	@psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}" -c "SHOW STATS;"
	@echo ""
	@echo "=== Server Connections ==="
	@psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}" -c "SHOW SERVERS;"
	@echo ""
	@echo "=== Client Connections ==="
	@psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}" -c "SHOW CLIENTS;"

# Open interactive PgBouncer admin console
dev-pgbouncer-admin:
	psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}"

# Reload PgBouncer configuration without restarting container
dev-pgbouncer-reload:
	@echo "Reloading PgBouncer configuration..."
	@psql "${PGBOUNCER_URL:-postgresql://${PGBOUNCER_ADMIN_USER:-postgres}:${PGBOUNCER_ADMIN_PASSWORD:-password}@localhost:6432/pgbouncer}" -c "RELOAD;" -q
	@echo "✓ Configuration reloaded successfully"

# Update pgbouncer_auth password across all configuration files
dev-pgbouncer-password password:
	@echo "⚠️  Updating pgbouncer_auth password in all configuration files"
	@echo ""
	@echo "1. Updating userlist.txt (plaintext password)..."
	@echo '"pgbouncer_auth" "{{password}}"' > docker/dev/pgbouncer/userlist.txt
	@echo "   ✓ docker/dev/pgbouncer/userlist.txt updated"
	@echo ""
	@echo "2. Remember to update .env file:"
	@echo "   PGBOUNCER_AUTH_PASSWORD={{password}}"
	@echo ""
	@echo "3. Remember to update docker/scripts/init-timescale.sql (line 42):"
	@echo "   PASSWORD '{{password}}'"
	@echo ""
	@echo "4. Restart containers:"
	@echo "   just dev-down && just dev-up"

# ─── Production ───────────────────────────────────────────────────────────────

# Build the production Docker image locally (tagged peebot:local)
prod-build:
	docker build -f docker/prod/Dockerfile -t peebot:local .

# Run pending database migrations against the running production web container
prod-migrate:
	docker exec peebot_web_prod python manage.py migrate

# Open an interactive Django shell inside the production web container
prod-shell:
	docker exec -it peebot_web_prod python manage.py shell

# Seed telemetry channels into the production database
prod-seed:
	docker exec peebot_web_prod python manage.py seed_channels

# Tail logs for all production services (Ctrl+C to stop)
prod-logs:
	{{prod-compose}} logs -f
