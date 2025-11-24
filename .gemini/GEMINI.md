# PeeBot Project Context

## Project Overview
PeeBot is a Django modular monolith designed to ingest real-time ISS telemetry data, store it in TimescaleDB, and run independent analytics modules. Its primary feature is detecting when the Urine Processor Assembly is active and posting humorous tweets about it.

## Architecture

### Core Principles
- **Pattern:** Modular Monolith.
- **Single Source of Truth:** TimescaleDB stores all telemetry data and analytics results. Redis is ephemeral only (Celery queue, Channels layer).
- **Polling Architecture:** Analytics modules poll the database periodically using Celery Beat. This decouples ingestion from analytics and enables sliding window analysis and historical replay.

### Module Dependencies & Ownership
The system is organized into independent modules in `apps/`.
- **`core`**: Shared utilities, base models, DRF serializers.
- **`telemetry_storage`**: **OWNS** `TelemetryReading` and `TelemetryChannel` models.
- **`telemetry_ingestion`**: Lightstreamer client, validation. **Imports** models from `telemetry_storage`.
- **`event_processors`**: Analytics logic (PeeBot). **OWNS** `DetectedEvent` and `ProcessorState` models. Queries storage models.
- **`dashboards`**: Web UI and WebSocket consumers. Queries all models.

**Dependency Graph:**
```
core (base classes)
  ↑
telemetry_storage (owns telemetry models)
  ↑                           ↑
telemetry_ingestion       event_processors
(imports storage models)  (queries storage models)
                              ↑
                          dashboards
                    (queries all models)
```

### Data Flow
1.  **Ingestion:** Lightstreamer → Validation (DRF serializers) → Enrichment (event_id, timestamps) → Repository → TimescaleDB
2.  **Analytics:** Celery Beat triggers → Query ProcessorState → Query TelemetryReading (sliding window) → Detect events → Write DetectedEvent → Update ProcessorState
3.  **Dashboards:** HTTP/WebSocket → Query TimescaleDB → Render UI

## Technology Stack
- **Language:** Python 3.14+
- **Framework:** Django 5.2+, Django REST Framework, Django Channels
- **Database:** PostgreSQL 15+ with TimescaleDB
- **Queue/Cache:** Redis, Celery, Celery Beat
- **Package Manager:** `uv`
- **Frontend:** HTMX for dynamic updates
- **Deployment:** Docker, Coolify (Nginx, Gunicorn, Daphne)

## Database & Optimizations (TimescaleDB)
- `TelemetryReading` is a hypertable with time-based partitioning (1-day chunks).
- Automatic compression after 7 days.
- Retention policy: drop chunks older than 30 days.
- Continuous aggregates used for dashboard queries.

## Development Commands

### Package Management (`uv`)
- **Sync dependencies:** `uv sync`
- **Add package:** `uv add <package>` (Use `--dev` for dev dependencies)
- **Remove package:** `uv remove <package>`
- **Run command in venv:** `uv run <command>`

### Server & Services
- **Start Dev Stack (Docker):** `just dev-up`
- **Stop Dev Stack:** `just dev-down`
- **Django Dev Server:** `uv run python manage.py runserver`
- **Lightstreamer Ingestion:** `uv run python manage.py run_lightstreamer`
- **Celery Worker:** `uv run celery -A config worker --loglevel=info`
- **Celery Beat:** `uv run celery -A config beat --loglevel=info`

### Database
- **Migrations:** `uv run python manage.py migrate`
- **Make Migrations:** `uv run python manage.py makemigrations`
- **Django Shell:** `uv run python manage.py shell`
- **DB Shell:** `uv run python manage.py dbshell`
- **Flush DB:** `uv run python manage.py flush` (Development only)

### Testing & Quality
- **Run All Tests:** `uv run pytest`
- **Run Specific Test:** `uv run pytest tests/test_processors.py`
- **With Coverage:** `uv run pytest --cov=apps`
- **Lint:** `uv run ruff check .`
- **Type Check:** `uv run mypy apps/`

## Critical Implementation Guidelines

### Model Import Pattern
**CRITICAL:** `telemetry_ingestion` does NOT define database models. It imports them from `telemetry_storage`.
```python
from apps.telemetry_storage.models import TelemetryReading, TelemetryChannel
```

### Repository Pattern
Use the repository pattern (in `telemetry_storage/repositories.py`) to abstract database operations. This separates business logic from data access and facilitates testing.

### Async Support
- Use Django async views for ingestion endpoints.
- Use async ORM operations for database writes.
- Lightstreamer client runs as an async management command.

## Common Patterns

### Adding a New Analytics Module
1.  Create a processor class inheriting from `BaseProcessor` in `event_processors/processors/`.
2.  Implement detection logic using sliding window queries.
3.  Add Celery periodic task in `event_processors/tasks.py`.
4.  Configure schedule in `config/celery.py`.
5.  Create management command for manual testing.

### Querying Time-Series Data
```python
# Get recent readings for a channel
readings = TelemetryReading.objects.filter(
    channel__item_id='NODE3000004',
    timestamp__gte=timezone.now() - timedelta(minutes=10)
).order_by('timestamp')
```

## Directory Structure
- `apps/`: Application modules.
  - `core/`: Shared utilities, base models.
  - `telemetry_storage/`: Owns `TelemetryReading` and `TelemetryChannel`.
  - `telemetry_ingestion/`: Lightstreamer client and data validation.
  - `event_processors/`: Analytics logic (PeeBot), owns `DetectedEvent`.
  - `dashboards/`: Web UI and WebSocket consumers.
- `config/`: Django settings.
- `docker/`: Docker configuration.
- `tests/`: Integration tests.