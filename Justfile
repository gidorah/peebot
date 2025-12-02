# Development automation recipes for PeeBot
set shell := ["bash", "-c"]
set dotenv-load := true

dev-compose := "docker compose -f docker/dev/docker-compose.yml"

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

# Apply database migrations via the web container
dev-migrate:
	{{dev-compose}} run --rm web uv run python manage.py migrate

# Create a Django superuser through the web container
dev-createsuperuser:
	{{dev-compose}} run --rm web uv run python manage.py createsuperuser

# Run pytest suite (accepts additional args)
dev-test *args:
	{{dev-compose}} run --rm web uv run pytest {{args}}

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
