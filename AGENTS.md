# PeeBot Project Context

## Project Overview
PeeBot is a Django modular monolith for ISS telemetry analytics (TimescaleDB), specifically detecting Urine Processor Assembly activity (`NODE3000004`) to post humorous tweets.

## Architecture & Core Principles
- **Pattern:** Modular Monolith. **Single Source of Truth:** TimescaleDB. **Redis:** Ephemeral (Queue/Cache).
- **Polling:** Analytics modules poll DB via Celery Beat (decoupled ingestion/analytics). Allows sliding window analysis & replay.
- **TimescaleDB:** `TelemetryReading` is a hypertable (1-day chunks, 7-day compression, 30-day retention).

### Module Ownership (Strict)
- **`core`**: Shared utils, base models, serializers.
- **`telemetry_storage`**: **OWNS** `TelemetryReading`, `TelemetryChannel`.
- **`telemetry_ingestion`**: Imports models from `telemetry_storage`. **NO** model definitions.
- **`event_processors`**: **OWNS** `DetectedEvent`. Queries `telemetry_storage`.
- **`dashboards`**: Web UI. Queries all models.

**Dependency Flow:** `ingestion` → `storage` ← `processors` → `dashboards`

## Critical Implementation Rules
1.  **Model Imports:** `telemetry_ingestion` MUST import from `apps.telemetry_storage.models`. Never define storage models in ingestion.
2.  **Repository Pattern:** Use `apps.telemetry_storage.repositories` for DB operations.
3.  **Async:** Use Django async views for ingestion and async ORM for writes.
4.  **Lightstreamer:** Runs as an async management command.

## Development Cheatsheet

### Package Management (uv)
- `uv sync`: Sync dependencies.
- `uv add <pkg> [--dev]`: Add package.
- `uv run <cmd>`: Run in venv (e.g., `uv run python manage.py ...`).

### Services & Commands
- **Start Stack:** `just dev-up` / `just dev-down`
- **Dev Server:** `uv run python manage.py runserver`
- **Ingestion:** `uv run python manage.py run_lightstreamer`
- **Celery Worker:** `uv run celery -A config worker --loglevel=info`
- **Celery Scheduler:** `uv run celery -A config beat --loglevel=info`
- **DB Shell:** `uv run python manage.py dbshell`

### Quality & Testing
- **Test:** `uv run pytest`
- **Coverage:** `uv run pytest --cov=apps`
- **Lint:** `uv run ruff check .`
- **Type Check:** `uv run mypy apps/`

## Common Patterns

### New Analytics Module
1. Inherit `BaseProcessor` in `event_processors/processors/`.
2. Implement sliding window logic (query `TelemetryReading`).
3. Schedule in `config/celery.py`.

### Time-Series Query (Sliding Window)
```python
from apps.telemetry_storage.models import TelemetryReading
# Example: Last 10 minutes for Node 3
readings = TelemetryReading.objects.filter(
    channel__item_id='NODE3000004',
    timestamp__gte=timezone.now() - timedelta(minutes=10)
).order_by('timestamp')
```

## Testing & Deployment Guidelines
- **Testing Strategy:**
  - Use `model_bakery` for test data factories.
  - **Mock external APIs** (Lightstreamer, Twitter) in tests.
  - Use a separate test database with TimescaleDB enabled.
- **Deployment Stack:** Single VPS with Coolify. Nginx (Proxy) → Gunicorn (HTTP) / Daphne (WSGI/ASGI).

## Task Management
- **GitHub Issues:** Primary source for task management and tracking.
- **Tooling:** Use `gh` CLI for interactions (e.g., `gh issue list`, `gh issue create`, `gh issue view <id>`).

## Directory Structure
- `apps/core`: Shared utils, base exceptions.
- `apps/telemetry_storage`: DB Models (`TelemetryReading`), Repositories.
- `apps/telemetry_ingestion`: Lightstreamer client, Validation.
- `apps/event_processors`: Analytics logic (`DetectedEvent`), Tasks.
- `apps/dashboards`: UI/WebSockets.
- `config/`: Django settings (`celery.py`).
- `docker/`: Docker configs (`init-timescale.sql`).
