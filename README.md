# PeeBot - ISS Telemetry Data Analytics System

A Django modular monolith that ingests real-time ISS telemetry data from Lightstreamer, stores it in TimescaleDB, and runs independent analytics modules to detect events. The primary module (PeeBot) detects when astronauts use the Urine Processor Assembly and posts humorous updates to Bluesky.

## Overview

This system implements a **modular monolith architecture** using Django, where each module represents a bounded context with clear responsibilities. The architecture prioritizes:

- **Single Source of Truth**: TimescaleDB stores all telemetry data and analytics results
- **Polling Architecture**: Analytics modules poll database periodically using Celery Beat
- **Independence**: Each analytics module operates independently with its own schedule
- **Async Support**: Leverages Django's ASGI for real-time ingestion
- **Single Deployment Unit**: One codebase, one deployment, simpler operations
- **Operational Visibility**: Built-in liveness/readiness probes and OpenAPI docs for HTTP surfaces

## Project Structure

```
peebot/
|-- manage.py                      # Django management script
|-- Justfile                       # Task runner recipes (just)
|-- pyproject.toml                 # Python dependencies (uv)
|-- config/                        # Django project configuration
|   |-- __init__.py
|   |-- celery.py                  # Celery app configuration
|   |-- settings/                  # Split settings for environments
|   |   |-- __init__.py
|   |   |-- base.py                # Shared settings
|   |   |-- development.py         # Local development
|   |   |-- production.py          # Production deployment
|   |   +-- testing.py             # Test environment
|   |-- asgi.py                    # ASGI application
|   |-- wsgi.py                    # WSGI application
|   +-- urls.py                    # URL routing
|
|-- apps/                          # All Django application modules
|   |-- core/                      # Shared utilities and base models
|   |   |-- models.py              # Abstract base models (UUID7, TimeStamped, SoftDelete)
|   |   |-- logging.py             # Custom SeqHandler for structured logging
|   |   |-- serializers.py         # DRF base serializers
|   |   |-- utils.py               # Helper functions
|   |   +-- exceptions.py          # Custom exceptions
|   |
|   |-- telemetry_storage/         # Data persistence layer
|   |   |-- models.py              # TelemetryReading, TelemetryChannel
|   |   |-- repositories.py        # Data access layer
|   |   +-- management/commands/   # seed_channels.py
|   |
|   |-- telemetry_ingestion/       # Lightstreamer data ingestion
|   |   |-- services/              # Client, validators, enrichers
|   |   +-- management/commands/   # run_lightstreamer.py
|   |
|   |-- event_processors/          # Analytics and event detection
|   |   |-- models.py              # DetectedEvent, ProcessorState, SocialPost
|   |   |-- processors/            # PeeBot and other detectors
|   |   |-- services/              # Bluesky client, joke generator
|   |   |-- tests/                 # Unit tests for processors and services
|   |   +-- tasks.py               # Celery periodic tasks
|   |
|   +-- dashboards/                # Web interface (planned)
|       +-- views.py               # Dashboard views
|
|-- docker/                        # Container infrastructure
|   |-- dev/                       # Development Docker Compose, Dockerfile, PgBouncer
|   |-- prod/                      # Production Docker Compose, Dockerfile, entrypoint
|   +-- scripts/                   # TimescaleDB init scripts
|
|-- tests/                         # Project-wide integration tests
|-- .env                           # Environment variables (not in git)
|-- .env.example                   # Environment variables template
+-- .env.production.example        # Production environment template (Coolify)
```

## Module Dependencies

```
core (base models, utilities)
  ^
  |
  | inherits from
  |
telemetry_storage (owns: TelemetryReading, TelemetryChannel)
  ^                           ^
  |                           |
  | imports models            | queries database
  |                           |
telemetry_ingestion       event_processors
(writes telemetry)        (owns: DetectedEvent, ProcessorState, SocialPost)
                              ^
                              |
                              | queries all data
                              |
                          dashboards
                       (no model ownership)
```

**Key Principles**:
- Each module owns specific database models
- Modules can import models from other modules
- Repository pattern abstracts database access
- Analytics modules query via database, not direct imports

## Quick Start

### Prerequisites

- **Python 3.14+**
- **uv** (fast Python package manager)
- **PostgreSQL** with TimescaleDB extension (for production)
- **Redis** (for Celery task queue)

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd peebot
   ```

2. **Install dependencies with uv**:
   ```bash
   # uv automatically creates and manages virtual environment
   uv sync
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Run migrations**:
   ```bash
   uv run python manage.py migrate
   ```

5. **Create a superuser** (optional):
   ```bash
   uv run python manage.py createsuperuser
   ```

6. **Run the development server**:
   ```bash
   uv run python manage.py runserver
   ```

The application will be available at `http://localhost:8000`

### HTTP Endpoints

The Django app exposes a small set of operational and API endpoints:

| Endpoint | Purpose |
|---------|---------|
| `GET /healthz` | Liveness probe for the web process |
| `GET /readyz` | Readiness probe that checks PostgreSQL and Redis reachability |
| `GET /api/v1/channels/` | Paginated, read-only list of telemetry channels |
| `GET /api/v1/events/` | Paginated, read-only list of detected events |
| `POST /api/v1/telemetry/inject/` | Manual telemetry injection for debugging/testing (`DEBUG=True` only) |
| `GET /api/schema/` | OpenAPI schema |
| `GET /api/docs/` | Swagger UI for the public API |

### Task Runner (`just`)

This project uses [`just`](https://github.com/casey/just) as its task runner. Key commands:

**Development:**

| Command | Description |
|---------|-------------|
| `just dev-up` | Start the full development stack (Docker Compose). Accepts optional service names. |
| `just dev-down` | Stop and remove development containers |
| `just dev-stop` | Stop containers without removing them |
| `just dev-logs [service]` | Tail logs for a service (default: `web`) |
| `just dev-shell [service]` | Open interactive shell in container (default: `web`) |
| `just dev-django-shell` | Open Django shell in web container |
| `just dev-python <args>` | Run Python script/command in web container |
| `just dev-migrate` | Run migrations via PgBouncer |
| `just dev-migrate-direct` | Run migrations directly (bypasses PgBouncer — for heavy ops) |
| `just dev-createsuperuser` | Create Django superuser in container |
| `just dev-test [args]` | Run pytest suite in Docker container |
| `just dev-check` | Run `ruff check` and `mypy` in container |
| `just dev-psql` | Quick `psql` access to TimescaleDB |
| `just dev-pgbouncer` | Show PgBouncer pool statistics (quick view) |
| `just dev-pgbouncer-stats` | Detailed PgBouncer stats (pools, stats, servers, clients) |
| `just dev-pgbouncer-admin` | Interactive PgBouncer admin console |
| `just dev-pgbouncer-reload` | Reload PgBouncer configuration without restart |
| `just dev-pgbouncer-password <pw>` | Update `pgbouncer_auth` password across all config files |

**Local (no Docker):**

| Command | Description |
|---------|-------------|
| `just test [args]` | Run tests locally (uses `.env.local` for direct DB connection) |
| `just lint` | Run linting locally |

**Production:**

| Command | Description |
|---------|-------------|
| `just prod-build` | Build production Docker image (`peebot:local`) |
| `just prod-migrate` | Run pending migrations in production container |
| `just prod-shell` | Open Django shell in production container |
| `just prod-seed` | Seed telemetry channels in production database |
| `just prod-logs` | Tail logs for all production services |

Run `just` with no arguments to see all available recipes, or see the [Justfile](Justfile) for the full list.

## Containerized Development (PgBouncer pooling)

To run the full stack in containers with PgBouncer session pooling:

1. Copy `.env.example` to `.env` and adjust credentials if needed. The defaults match the compose setup (TimescaleDB on `localhost:5432`, PgBouncer on `localhost:6432`).
2. Build and start the services:
   ```bash
   docker compose -f docker/dev/docker-compose.yml up --build -d timescaledb pgbouncer redis
   docker compose -f docker/dev/docker-compose.yml up --build web worker beat ingestion
   ```
3. Run database migrations (one-off):
   ```bash
   docker compose -f docker/dev/docker-compose.yml run --rm web uv run python manage.py migrate
   ```
4. The Django dev server listens on `http://localhost:8000`, PgBouncer exposes `localhost:6432`, and TimescaleDB remains reachable directly via `localhost:5432`.
5. **Logging (Seq)**: Access the centralized log dashboard at `http://localhost:5341`.
   - **Username**: `admin`
   - **Password**: `password`
   > If you change the database name or credentials, update both `.env` and `docker/dev/pgbouncer/pgbouncer.ini` so PgBouncer can route connections correctly.

### PgBouncer Configuration

PgBouncer acts as a connection pooler between Django and TimescaleDB, optimizing resource usage and performance.

#### Pool Parameters (Development)

- **pool_mode=session** – Each client gets a dedicated backend connection for their entire session. Required for Django ORM compatibility (supports prepared statements, temp tables, locks).
- **server_reset_query=DISCARD ALL** – Clears prepared statements, temp tables, advisory locks, and session GUC changes before returning connections to the pool. Prevents state bleed between Django requests.
- **auth_type=scram-sha-256 + auth_query** – Hybrid authentication: `pgbouncer_auth` superuser in `userlist.txt`, application users validated via `SELECT usename, passwd FROM pg_shadow WHERE usename=$1`.
- **default_pool_size=10** – Backend connections per database (optimized for dev: web + worker + beat + manual ops)
- **min_pool_size=2** – Warm connections for instant query response
- **reserve_pool_size=3** – Emergency pool for burst traffic
- **max_client_conn=50** – Max total client connections (5x typical usage for easy leak detection)
- **max_db_connections=15** – Hard limit to PostgreSQL (10 + 3 + 2 buffer)
- **server_idle_timeout=600s** – Close idle backend after 10 min
- **server_lifetime=3600s** – Recycle connections hourly
- **query_timeout=30s** – Kill queries running >30s (catch bad code early)
- **idle_transaction_timeout=60s** – Kill idle transactions after 60s

#### Pool Sizing: Development vs Production

| Parameter | Development | Production | Rationale |
|-----------|-------------|------------|-----------|
| `default_pool_size` | 10 | 25 | Dev: web(2) + worker(2) + beat(1) + ops(3) ≈ 10<br/>Prod: web(8) + worker(4) + daphne(4) + beat(1) + ops(3) ≈ 25 |
| `min_pool_size` | 2 | 5 | Warm connections for faster response |
| `reserve_pool_size` | 3 | 10 | Larger burst handling in production |
| `max_client_conn` | 50 | 200 | More concurrent clients in production |
| `max_db_connections` | 15 | 40 | Hard limit scales with pool size |
| `query_timeout` | 30s | 60s | Tighter in dev to catch bad queries |

#### Password Management

**⚠️ IMPORTANT**: When using `auth_query`, the `pgbouncer_auth` password must be stored in **plaintext** in `userlist.txt`. This is a PgBouncer requirement because SCRAM-SHA-256 authentication needs the actual password to compute challenge responses. See [PgBouncer documentation](https://www.pgbouncer.org/config.html#auth_file) for details.

**Why plaintext is required**: PgBouncer must authenticate to PostgreSQL using SCRAM-SHA-256 challenge-response protocol, which cannot be computed from password hashes. This is still more secure than the alternative (storing all user passwords in plaintext), as only one password is in plaintext while all application users authenticate dynamically against PostgreSQL.

**⚠️ CRITICAL**: Three locations must stay synchronized:
1. `docker/dev/pgbouncer/userlist.txt` - **Plaintext password**
2. `.env` file - `PGBOUNCER_AUTH_PASSWORD` variable
3. `docker/scripts/init-timescale.sql` - `CREATE ROLE` password

**To update passwords**:
```bash
# 1. Update userlist.txt with plaintext password
echo '"pgbouncer_auth" "your_new_password"' > docker/dev/pgbouncer/userlist.txt

# 2. Update .env
echo "PGBOUNCER_AUTH_PASSWORD=your_new_password" >> .env

# 3. Update init-timescale.sql (line 42 - inside EXECUTE block)

# 4. Rebuild containers
docker compose -f docker/dev/docker-compose.yml down
docker compose -f docker/dev/docker-compose.yml up --build -d
```

#### Monitoring & Admin Console

Access the PgBouncer admin console:
```bash
# Show pool statistics
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "SHOW POOLS;"

# Show detailed statistics
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "SHOW STATS;"

# Show active server connections
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "SHOW SERVERS;"

# Show client connections
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "SHOW CLIENTS;"

# Reload configuration without restart
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "RELOAD;"
```

**Understanding SHOW POOLS output**:
- `cl_active`: Active client connections
- `cl_waiting`: Clients waiting for a connection
- `sv_active`: Active server (PostgreSQL) connections
- `sv_idle`: Idle server connections in pool
- `maxwait`: Max time a client waited for connection (should be 0)

#### Two Ways to Access the Database

1. **Via PgBouncer (port 6432)** - RECOMMENDED for application code
   - Connection pooling and management
   - Optimized for Django web/worker/beat processes
   - URL: `postgresql://user:password@localhost:6432/peebot`

2. **Direct to TimescaleDB (port 5432)** - For admin/tooling only
   - Direct PostgreSQL access
   - For psql, pgAdmin, database migrations, manual queries
   - URL: `postgresql://user:password@localhost:5432/peebot`

#### Troubleshooting

**Connection Refused**:
```bash
# Check PgBouncer is running
docker ps | grep pgbouncer

# Check PgBouncer logs
docker logs peebot_pgbouncer_dev

# Verify health check
docker compose -f docker/dev/docker-compose.yml ps
```

**Pool Exhausted (maxwait > 0)**:
```bash
# Check who's holding connections
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "SHOW CLIENTS;"

# Increase pool size in pgbouncer.ini temporarily
# Or investigate connection leaks in Django code
```

**Authentication Failed**:
```bash
# Verify passwords are in sync
docker exec peebot_timescaledb_dev psql -U postgres -d peebot -c "SELECT rolname FROM pg_roles WHERE rolname='pgbouncer_auth';"

# Regenerate userlist.txt hash
./docker/dev/pgbouncer/generate_userlist.sh pgbouncer_auth <password>
```

**Slow Queries**:
```bash
# Check for long-running queries
psql postgresql://postgres:password@localhost:6432/pgbouncer -c "SHOW POOLS;" | grep maxwait

# Lower query_timeout in pgbouncer.ini for faster failure
```

### Environment Configuration

The `.env` file contains configuration for your environment. Key variables:

```bash
# Django Settings Module (optional - has defaults)
# DJANGO_SETTINGS_MODULE=config.settings.development

# Django Secret Key (REQUIRED)
SECRET_KEY=your-secret-key-here

# Debug mode
DEBUG=True

# Allowed hosts (comma-separated)
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/peebot
POSTGRES_DB=peebot
POSTGRES_USER=peebot_user
POSTGRES_PASSWORD=password

# PgBouncer
PGBOUNCER_AUTH_PASSWORD=password

# Redis / Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Seq Logging (development)
SEQ_SERVER_URL=http://localhost:5341
SEQ_API_KEY=
SERVICE_NAME=peebot

# Event processor integrations
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=deepseek/deepseek-chat
JOKE_GENERATOR_MAX_RETRIES=3
JOKE_GENERATOR_BASE_DELAY=1.0
BLUESKY_HANDLE=your-handle.bsky.social
BLUESKY_APP_PASSWORD=your-app-password
BLUESKY_COOLDOWN_MINUTES=30
```

> **`.env.local`**: Local development commands like `just test` use `.env.local` for a direct database connection that bypasses PgBouncer. This is necessary because pytest needs to create and drop test databases, which PgBouncer cannot route. Copy `.env` to `.env.local` and set `DATABASE_URL` to the direct TimescaleDB connection (port `5432`). You can also set `TEST_DATABASE_URL` to override the test database connection independently.

> **`.env.production.example`**: A comprehensive production environment template is provided at `.env.production.example`. It includes Coolify-specific guidance, password constraints, and distinguishes between variables set in the Coolify UI versus Docker Compose. Copy it and fill in secrets before deploying.

## Settings Management

This project uses Django's standard settings pattern with environment-specific files:

- **`config/settings/base.py`**: Shared settings for all environments
- **`config/settings/development.py`**: Local development settings (Seq logging, `django-structlog`)
- **`config/settings/production.py`**: Production deployment settings (Gunicorn, WhiteNoise, security headers)
- **`config/settings/testing.py`**: Test environment (inherits development, disables Seq, uses faster password hasher)

### Switching Environments

```bash
# Development (default for manage.py)
uv run python manage.py runserver

# Production (default for wsgi.py/asgi.py)
DJANGO_SETTINGS_MODULE=config.settings.production uv run python manage.py runserver

# Custom settings
DJANGO_SETTINGS_MODULE=config.settings.testing uv run pytest
```

## Technology Stack

### Core Framework
- **Django 5.2+** - Web framework with ORM, admin, authentication
- **Django REST Framework** - API development and serialization
- **django-environ** - Environment variable parsing (12-factor app support)

### Database
- **TimescaleDB** - PostgreSQL extension for time-series data
- **psycopg 3** - PostgreSQL adapter with connection pooling (`psycopg[binary,pool]`)

### Task Queue
- **Celery** - Distributed task queue
- **django-celery-beat** - Database-backed periodic task scheduler
- **Redis** - Celery broker and result backend

### External APIs
- **Lightstreamer Client** - ISS telemetry ingestion
- **atproto** - Bluesky AT Protocol SDK for social media posting
- **OpenAI client** - Used via OpenRouter for AI-generated jokes (DeepSeek model)

### Data Validation
- **Pydantic V2** - High-performance data validation for ingestion
- **defusedxml** - Secure XML parsing for PUI channel list

### Production
- **Gunicorn** - WSGI HTTP server
- **WhiteNoise** - Static file serving (with compression)

### Logging
- **Structlog** - Structured logging instrumentation
- **Seq** - Centralized structured log dashboard (development)

### Package Management
- **uv** - Fast Python package manager and virtual environment tool

### Development Tools
- **pytest** / **pytest-django** / **pytest-asyncio** - Testing framework
- **model-bakery** - Test data factories
- **ruff** - Fast Python linter and formatter
- **mypy** / **django-stubs** - Static type checking
- **pre-commit** - Pre-commit hook framework
- **Flower** - Celery monitoring web UI
- **debugpy** - Remote debugging support

## Development Commands

### Package Management (uv)

```bash
# Sync dependencies and update virtual environment
uv sync

# Add new package
uv add <package-name>

# Add development dependency
uv add --dev <package-name>

# Remove package
uv remove <package-name>

# Run commands in uv environment (alternative to activation)
uv run python manage.py <command>
```

### Django Management

```bash
# Run development server
uv run python manage.py runserver

# Create migrations
uv run python manage.py makemigrations

# Apply migrations
uv run python manage.py migrate

# Access Django shell
uv run python manage.py shell

# Access database shell
uv run python manage.py dbshell

# Create superuser
uv run python manage.py createsuperuser
```

### Celery

```bash
# Run Celery worker
uv run celery -A config worker --loglevel=info

# Run Celery Beat scheduler
uv run celery -A config beat --loglevel=info

# Inspect scheduled tasks
uv run celery -A config inspect scheduled

```

### Testing

> **Important**: Do not run `pytest` directly. Use `just` commands to ensure
> correct environment setup (database connection, env files, Docker services).

```bash
# Run tests locally (requires .env.local with direct DB connection)
just test

# Run tests in Docker container
just dev-test

# Pass additional pytest arguments
just test -k "test_ingestion"
just dev-test --cov=apps
```

Unit tests are located in `apps/<module>/tests/`, integration tests in `tests/`.

### Pull Request CI

GitHub Actions runs the test suite automatically for pull requests targeting `main` when the PR is:

- opened,
- updated with new commits,
- reopened.

The workflow uses a TimescaleDB service container and runs the canonical project test command:

```bash
just test
```

In CI, `just test` receives a CI-specific `DOTENV_PATH` so the workflow can use an ephemeral `.env.ci` file instead of a developer-local `.env.local`.

To reproduce the CI execution path locally, create a CI-style env file and run:

```bash
DOTENV_PATH=.env.ci just test
```

### Code Quality

```bash
# Run linter
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Type checking
uv run mypy apps/
```

## Architecture

### Modular Monolith Pattern

All modules exist in a single codebase and deployment unit with clear boundaries:

- Each module has clear responsibilities
- Modules own their database models
- Single shared database
- Communication via database queries or Python imports
- Repository pattern abstracts data access

### Model Ownership

Database models are owned by specific modules:

| Module | Owns Models | Purpose |
|--------|-------------|---------|
| `core` | Abstract base models | Reusable model mixins (timestamps, UUIDs, soft-delete) |
| `telemetry_storage` | `TelemetryReading`, `TelemetryChannel` | ISS telemetry data persistence |
| `event_processors` | `DetectedEvent`, `ProcessorState`, `SocialPost` | Analytics results, state, and social posts |
| `dashboards` | No models | Queries data from other modules |
| `telemetry_ingestion` | No models | Writes to `telemetry_storage` models |

### Data Flow

```
ISS Lightstreamer Feed
         |
         v
[Lightstreamer Client]
         |
         v
[Validation Service] <- Pydantic
         |
         v
[Enrichment Service] <- Add event_id, timestamps
         |
         v
[Repository Layer]
         |
         v
   [TimescaleDB]
   (Single Source)
         |
         v
[Analytics Modules] <- Poll every 30s
         |
         v
[DetectedEvent Table]
         |
         v
[External Actions] <- Bluesky, Email, etc.
```

### Polling Architecture

Analytics modules use a **polling pattern**:

1. Celery Beat triggers periodic task (e.g., every 30 seconds)
2. Query `ProcessorState` for `last_processed_timestamp` timestamp
3. Query `TelemetryReading` for new data since last check
4. Analyze sliding window (e.g., last 10 minutes)
5. Detect events and store results in `DetectedEvent`
6. Update `ProcessorState` with current timestamp

## Event Processors

The `event_processors` module runs polling-based analytics over recent telemetry
windows. The initial processor, `PeeBotProcessor`, detects UPA tank fill events
using a **net-change-over-window algorithm** against the `NODE3000005` channel
and can publish a short Bluesky post with an AI-generated joke when a valid event is
found. Processor state is stored in `ProcessorState` to ensure safe resumption
after restarts.

### Celery Task Configuration

- **Schedule**: Every 30 seconds via Celery Beat
- **Task**: `apps.event_processors.tasks.run_peebot_processor`
- **Reliability**: `acks_late=True`, auto-retry on `OperationalError` (3 retries, exponential backoff)
- **Jitter**: Random 0-5s delay to prevent thundering herd on multi-worker deployments
- **Async bridge**: Task wraps async processor logic via `async_to_sync`

To run processors locally, start a Celery worker and beat scheduler, then
monitor scheduled tasks (see the Celery section above).

## Database Schema

### TelemetryReading (TimescaleDB Hypertable)

Stores individual telemetry readings with time-based partitioning:

- `id`: UUIDField (UUIDv7)
- `channel`: ForeignKey -> TelemetryChannel
- `timestamp`: DateTimeField (indexed)
- `value`: DecimalField
- `calibrated_data`: DecimalField (nullable)
- `status_class`: CharField (nullable) - Telemetry status classification
- `status_indicator`: CharField (nullable) - Status indicator value
- `status_color`: CharField (nullable) - Status color code
- `metadata`: JSONField
- `created_at`, `updated_at`: DateTimeField

**Optimizations**:
- Automatic time partitioning (1-day chunks)
- Automatic compression after 7 days
- Retention policy: drop chunks > 30 days
- Indexes: `(channel, timestamp DESC)`, `(created_at, timestamp)`
- Unique constraint: `(channel, timestamp)` — prevents duplicate readings

### TelemetryChannel

Metadata for ~400 ISS telemetry channels:

- `public_pui`: CharField (unique, e.g., "NODE3000005")
- `description`: CharField
- `ops_nom`: CharField
- `eng_nom`: CharField
- `unit`: CharField
- `deleted_at`: DateTimeField (Soft-delete for active state)
- `created_at`, `updated_at`: DateTimeField

Channels are seeded via the `seed_channels` management command from `PUIList.xml`.

### DetectedEvent

Analytics results from event processors:

- `id`: UUIDField (UUIDv7)
- `event_type`: CharField (e.g., 'urination')
- `channel_id`: CharField (PUI of the source channel, e.g., 'NODE3000005')
- `detected_at`: DateTimeField
- `confidence`: DecimalField (0.00-1.00, nullable)
- `metadata`: JSONField
- `created_at`, `updated_at`: DateTimeField

### SocialPost

Social media posts linked to detected events:

- `id`: UUIDField (UUIDv7)
- `event`: ForeignKey -> DetectedEvent
- `platform`: CharField (e.g., 'bluesky')
- `content`: TextField
- `external_id`: CharField (blank, default empty string — platform post ID)
- `posted_at`: DateTimeField (nullable)
- `status`: CharField (`pending`, `success`, `failed`)
- `error_message`: TextField (blank, default empty string)
- `created_at`, `updated_at`: DateTimeField

### ProcessorState

State tracking for analytics modules:

- `id`: UUIDField (UUIDv7)
- `processor_name`: CharField (unique, e.g., 'PeeBot')
- `last_processed_timestamp`: DateTimeField
- `last_run_at`: DateTimeField
- `state_data`: JSONField
- `created_at`, `updated_at`: DateTimeField

## Production Deployment

The project is designed for deployment on [Coolify](https://coolify.io/) with Traefik TLS termination and Docker Compose orchestration. All images are **baked** (no runtime volume mounts for code).

### Production Architecture

| Service | Image | Purpose |
|---------|-------|---------|
| `web` | `peebot:local` | Gunicorn WSGI server (runs migrations + `seed_channels` on start) |
| `worker` | `peebot:local` | Celery worker for async tasks |
| `beat` | `peebot:local` | Celery Beat scheduler |
| `ingestion` | `peebot:local` | Lightstreamer telemetry ingestion |
| `timescaledb` | Custom (baked init scripts) | TimescaleDB with PgBouncer auth user |
| `pgbouncer` | `bitnami/pgbouncer` | Connection pooling |
| `redis` | `redis:7-alpine` | Celery broker |

### Build & Deploy

```bash
# Build production image
just prod-build

# Run migrations
just prod-migrate

# Seed telemetry channels
just prod-seed

# Tail production logs
just prod-logs
```

### Production Configuration

Key production settings (`config/settings/production.py`):
- **WhiteNoise** for static file serving with compressed manifests
- **Security headers**: HSTS, secure cookies, `X-Frame-Options`, `X-Content-Type-Options`
- **`CSRF_TRUSTED_ORIGINS`** required (set in environment)
- **Gunicorn** as WSGI server (non-root user in container)
- Static files collected at Docker build time via multi-stage build

See `.env.production.example` for the full list of required environment variables.

## Performance Targets

- **Ingestion throughput**: 70 msg/sec nominal, 10K msg/sec tested
- **Ingestion latency**: P99 < 5 seconds
- **Dashboard updates**: P99 < 1 second
- **Analytics detection**: < 2 minutes

## License

[MIT License](LICENSE)

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and test thoroughly
4. Commit your changes: `git commit -m "Add my feature"`
5. Push to the branch: `git push origin feature/my-feature`
6. Submit a pull request

### Development Workflow

- Use `ruff` for code formatting and linting
- Run tests before committing: `just test`
- Follow Django best practices
- Keep modules independent and loosely coupled
- Document new features in code and README

## Links

- **Django Documentation**: https://docs.djangoproject.com/
- **Django REST Framework**: https://www.django-rest-framework.org/
- **TimescaleDB**: https://docs.timescale.com/
- **Celery**: https://docs.celeryproject.org/
- **uv Package Manager**: https://github.com/astral-sh/uv
- **Structlog**: https://www.structlog.org/
- **AT Protocol (Bluesky)**: https://atproto.com/
- **Coolify**: https://coolify.io/docs
