# PeeBot - ISS Telemetry Data Analytics System

A Django modular monolith that ingests real-time ISS telemetry data from Lightstreamer, stores it in TimescaleDB, and runs independent analytics modules to detect events. The primary module (PeeBot) detects when astronauts use the Urine Processor Assembly and posts humorous tweets.

## Overview

This system implements a **modular monolith architecture** using Django, where each module represents a bounded context with clear responsibilities. The architecture prioritizes:

- **Single Source of Truth**: TimescaleDB stores all telemetry data and analytics results
- **Polling Architecture**: Analytics modules poll database periodically using Celery Beat
- **Independence**: Each analytics module operates independently with its own schedule
- **Async Support**: Leverages Django's ASGI for real-time ingestion
- **Single Deployment Unit**: One codebase, one deployment, simpler operations

## Project Structure

```
peebot/
|-- manage.py                      # Django management script
|-- config/                        # Django project configuration
|   |-- __init__.py
|   |-- settings/                  # Split settings for environments
|   |   |-- __init__.py
|   |   |-- base.py                # Shared settings
|   |   |-- development.py         # Local development
|   |   +-- production.py          # Production deployment
|   |-- asgi.py                    # ASGI application (WebSocket support)
|   |-- wsgi.py                    # WSGI application
|   +-- urls.py                    # URL routing
|
|-- apps/                          # All Django application modules
|   |-- core/                      # Shared utilities and base models
|   |   |-- models.py              # Abstract base models
|   |   |-- serializers.py         # DRF base serializers
|   |   |-- utils.py               # Helper functions
|   |   +-- exceptions.py          # Custom exceptions
|   |
|   |-- telemetry_storage/         # Data persistence layer
|   |   |-- models.py              # TelemetryReading, TelemetryChannel
|   |   |-- repositories.py        # Data access layer
|   |   +-- managers.py            # Custom QuerySet managers
|   |
|   |-- telemetry_ingestion/       # Lightstreamer data ingestion
|   |   |-- services/              # Client, validators, enrichers
|   |   |-- views.py               # Manual injection endpoints
|   |   +-- management/commands/   # run_lightstreamer.py
|   |
|   |-- event_processors/          # Analytics and event detection
|   |   |-- models.py              # DetectedEvent, ProcessorState
|   |   |-- processors/            # PeeBot and other detectors
|   |   |-- services/              # Bluesky client, joke generator
|   |   +-- tasks.py               # Celery periodic tasks
|   |
|   +-- dashboards/                # Web interface
|       |-- views.py               # Dashboard views
|       |-- consumers.py           # WebSocket consumers
|       +-- templates/             # HTML templates
|
|-- static/                        # Static files (CSS, JS)
|-- templates/                     # Project-level templates
|-- tests/                         # Project-wide integration tests
|-- logs/                          # Application logs
|-- .env                           # Environment variables (not in git)
|-- .env.example                   # Environment variables template
|-- pyproject.toml                 # Python dependencies (uv)
+-- uv.lock                        # Locked dependencies
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
(writes telemetry)        (owns: DetectedEvent, ProcessorState)
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
- **Redis** (for Celery and Django Channels)

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

## Containerized Development (PgBouncer pooling)

To run the full stack in containers with PgBouncer session pooling:

1. Copy `.env.example` to `.env` and adjust credentials if needed. The defaults match the compose setup (TimescaleDB on `localhost:5432`, PgBouncer on `localhost:6432`).
2. Build and start the services:
   ```bash
   docker compose -f docker/dev/docker-compose.yml up --build -d timescaledb pgbouncer redis
   docker compose -f docker/dev/docker-compose.yml up --build web worker beat
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

# Database URL
DATABASE_URL=postgresql://user:password@localhost:5432/peebot

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

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

## Settings Management

This project uses Django's standard settings pattern with environment-specific files:

- **`config/settings/base.py`**: Shared settings for all environments
- **`config/settings/development.py`**: Local development settings
- **`config/settings/production.py`**: Production deployment settings

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
- **Django Channels** - WebSocket and async support

### Database
- **TimescaleDB** - PostgreSQL extension for time-series data
- **PostgreSQL 15+** - Relational database

### Task Queue
- **Celery** - Distributed task queue
- **Celery Beat** - Periodic task scheduler
- **Redis** - Celery broker and result backend

### External APIs
- **Lightstreamer Client** - ISS telemetry ingestion
- **atproto** - Bluesky AT Protocol SDK for social media posting

### Data Validation
- **Pydantic V2** - High-performance data validation for ingestion

### Package Management
- **uv** - Fast Python package manager and virtual environment tool

### Development Tools
- **pytest** - Testing framework
- **pytest-django** - Django testing utilities
- **pytest-asyncio** - Async testing support
- **model-bakery** - Test data factories
- **ruff** - Fast Python linter
- **mypy** - Static type checker
- **django-stubs** - Type stubs for Django
- **Seq** - Centralized structured logging
- **Structlog** - Structured logging instrumentation

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

# Run Flower monitoring dashboard
uv run celery -A config flower
# Dashboard available at http://localhost:5555

# Inspect scheduled tasks
uv run celery -A config inspect scheduled

```

### Testing

```bash
# Run all tests
uv run pytest

# Note: Unit tests are located in apps/<module>/tests/
# Integration tests are in tests/

# Run specific test file
uv run pytest tests/test_processors.py

# Run with coverage
uv run pytest --cov=apps

# Run async tests
uv run pytest -v --asyncio-mode=auto
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
| `event_processors` | `DetectedEvent`, `ProcessorState` | Analytics results and state |
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
[Analytics Modules] <- Poll every 30-60s
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
and can publish a short Bluesky post with a generated joke when a valid event is
found. Processor state is stored in `ProcessorState` to ensure safe resumption
after restarts.

To run processors locally, start a Celery worker and beat scheduler, then
monitor scheduled tasks (see the Celery section above).

## Database Schema

### TelemetryReading (TimescaleDB Hypertable)

Stores individual telemetry readings with time-based partitioning:

- `id`: UUIDField (UUIDv7)
- `channel`: ForeignKey -> TelemetryChannel
- `timestamp`: DateTimeField (indexed)
- `value`: DecimalField
- `calibrated_data`: DecimalField
- `created_at`: DateTimeField (Ingestion time)
- `metadata`: JSONField

**Optimizations**:
- Automatic time partitioning (1-day chunks)
- Automatic compression after 7 days
- Retention policy: drop chunks > 30 days
- Primary index: `(channel, timestamp DESC)`

### TelemetryChannel

Metadata for ~400 ISS telemetry channels:

- `id`: AutoField
- `public_pui`: CharField (unique, e.g., "NODE3000004")
- `description`: TextField
- `ops_nom`: CharField
- `eng_nom`: CharField
- `unit`: CharField
- `deleted_at`: DateTimeField (Soft-delete for active state)
- `created_at`, `updated_at`: DateTimeField

### DetectedEvent

Analytics results from event processors:

- `id`: AutoField
- `event_type`: CharField (e.g., 'urination')
- `channel_id`: CharField
- `detected_at`: DateTimeField
- `confidence`: DecimalField (0.0-1.0)
- `metadata`: JSONField
- `posted_at`: DateTimeField (nullable)
- `tweet_id`: CharField (nullable)

### ProcessorState

State tracking for analytics modules:

- `id`: AutoField
- `processor_name`: CharField (e.g., 'PeeBot')
- `last_processed_timestamp`: DateTimeField
- `last_run_at`: DateTimeField
- `state_data`: JSONField

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
- Run tests before committing: `uv run pytest`
- Follow Django best practices
- Keep modules independent and loosely coupled
- Document new features in code and README

## Links

- **Django Documentation**: https://docs.djangoproject.com/
- **Django REST Framework**: https://www.django-rest-framework.org/
- **TimescaleDB**: https://docs.timescale.com/
- **Celery**: https://docs.celeryproject.org/
- **uv Package Manager**: https://github.com/astral-sh/uv
