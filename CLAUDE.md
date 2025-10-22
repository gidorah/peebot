# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PeeBot is a Django modular monolith that ingests real-time ISS telemetry data from Lightstreamer, stores it in TimescaleDB, and runs independent analytics modules to detect events. The primary module (PeeBot) detects when astronauts use the Urine Processor Assembly and posts humorous tweets.

**Package Management**: This project uses `uv` for fast Python package management and virtual environment handling.

## Commands

### Environment Setup
```bash
# Sync dependencies and create/update virtual environment
# uv automatically manages the virtual environment
uv sync

# Install new package
uv add <package-name>

# Install dev dependency
uv add --dev <package-name>

# Remove package
uv remove <package-name>

# Run commands in uv-managed environment (alternative to activation)
uv run python manage.py runserver
```

### Development
```bash
# Run Django development server
uv run python manage.py runserver

# Run Lightstreamer ingestion (management command)
uv run python manage.py run_lightstreamer

# Run Celery worker
uv run celery -A config worker --loglevel=info

# Run Celery Beat scheduler
uv run celery -A config beat --loglevel=info

# Run PeeBot processor manually
uv run python manage.py run_pee_bot

# Create migrations
uv run python manage.py makemigrations

# Apply migrations
uv run python manage.py migrate

# Create Django admin superuser
uv run python manage.py createsuperuser
```

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_processors.py

# Run with coverage
uv run pytest --cov=apps

# Run async tests
uv run pytest -v --asyncio-mode=auto
```

### Database Management
```bash
# Access Django shell
uv run python manage.py shell

# Access database shell
uv run python manage.py dbshell

# Reset database (development only)
uv run python manage.py flush
```

## Architecture Overview

### Modular Monolith Structure

The system is a single Django application organized into independent modules:

```
apps/
├── core/                    # Shared utilities, base models, DRF serializers
├── telemetry_ingestion/    # Lightstreamer client, validation, enrichment
├── telemetry_storage/      # Models: TelemetryReading, TelemetryChannel
├── event_processors/       # Models: DetectedEvent, ProcessorState
└── dashboards/             # Web UI, WebSocket consumers
```

### Key Architectural Patterns

**Single Source of Truth**: TimescaleDB stores all telemetry data and analytics results. Redis is ephemeral only (Celery queue, Channels layer).

**Polling Architecture**: Analytics modules poll the database periodically using Celery Beat instead of event-driven architecture. This enables:
- Sliding window analysis (analyze last N minutes of data)
- Independent processor schedules
- Historical replay capability
- No coupling between ingestion and analytics

**Model Ownership**: Each module owns specific models:
- `telemetry_storage`: owns `TelemetryReading`, `TelemetryChannel`
- `event_processors`: owns `DetectedEvent`, `ProcessorState`
- Other modules import these models as needed

### Module Dependencies

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

1. **Ingestion**: Lightstreamer → Validation (DRF serializers) → Enrichment (event_id, timestamps) → Repository → TimescaleDB
2. **Analytics**: Celery Beat triggers → Query ProcessorState → Query TelemetryReading (sliding window) → Detect events → Write DetectedEvent → Update ProcessorState
3. **Dashboard**: HTTP/WebSocket → Query TimescaleDB → Render UI

### TimescaleDB Optimizations

- `TelemetryReading` is a hypertable with time-based partitioning (1-day chunks)
- Automatic compression after 7 days
- Retention policy: drop chunks older than 30 days
- Primary index: (channel_id, timestamp DESC)
- Continuous aggregates for dashboard queries

### PeeBot Detection Logic

Monitors channel `NODE3000004` (Urine Processor Assembly Tank Level):
1. Query last 10 minutes of readings
2. Detect increasing tank level trend
3. Generate humorous tweet
4. Post to Twitter (with 30-minute cooldown)
5. Store event in `DetectedEvent` table

## Critical Implementation Notes

### Model Import Pattern

`telemetry_ingestion` does NOT define database models. It imports `TelemetryReading` and `TelemetryChannel` from `telemetry_storage`:

```python
from apps.telemetry_storage.models import TelemetryReading, TelemetryChannel
```

This follows modular monolith principles where models are owned by one module and imported by others.

### Repository Pattern

Use repository pattern to abstract database operations:
- Provides clean separation between business logic and data access
- Makes testing easier with mock repositories
- Located in `telemetry_storage/repositories.py`

### Async Support

- Use Django async views for ingestion endpoints
- Use async ORM operations for database writes
- Lightstreamer client runs as async management command
- Django Channels handles WebSocket async consumers

### Celery Configuration

Configure periodic tasks in `config/celery.py`:

```python
app.conf.beat_schedule = {
    'run-pee-bot': {
        'task': 'apps.event_processors.tasks.run_pee_bot_detection',
        'schedule': 30.0,  # Every 30 seconds
    },
}
```

### Performance Targets

- Ingestion throughput: 70 msg/sec nominal, 10K msg/sec tested
- Ingestion latency: P99 < 5 seconds
- Dashboard updates: P99 < 1 second
- Analytics detection: < 2 minutes

## Technology Stack

- **uv**: Fast Python package manager and virtual environment tool
- **Django 5.2+**: Web framework
- **Django REST Framework**: API and serialization
- **Django Channels**: WebSocket support
- **TimescaleDB**: Time-series PostgreSQL extension
- **Celery + Celery Beat**: Background tasks and scheduling
- **Redis**: Celery broker, Channels layer (ephemeral only)
- **HTMX**: Dynamic frontend updates
- **Tweepy**: Twitter API integration
- **pytest**: Testing framework

## Deployment

Single VPS deployment with Coolify:
- Nginx: Reverse proxy, SSL termination, static files
- Gunicorn: WSGI server for HTTP (4-8 workers)
- Daphne: ASGI server for WebSockets
- Celery Workers: 2-4 background workers
- Celery Beat: Single scheduler process
- Lightstreamer Management Command: Long-running systemd service
- TimescaleDB: Single database instance
- Redis: Celery broker and Channels layer

## Testing Notes

- Use separate test database with TimescaleDB enabled
- Configure Django to create hypertables in test migrations
- Use `pytest-django`, `pytest-asyncio`, `channels.testing`
- Mock external APIs (Lightstreamer, Twitter) in tests
- Use `model_bakery` for test data factories

## Common Patterns

### Adding a New Analytics Module

1. Create processor class inheriting from `BaseProcessor` in `event_processors/processors/`
2. Implement detection logic using sliding window queries
3. Add Celery periodic task in `event_processors/tasks.py`
4. Configure schedule in `config/celery.py`
5. Create management command for manual testing
6. Store results in `DetectedEvent` table with unique `event_type`

### Querying Time-Series Data

```python
# Get recent readings for a channel
readings = TelemetryReading.objects.filter(
    channel__item_id='NODE3000004',
    timestamp__gte=timezone.now() - timedelta(minutes=10)
).order_by('timestamp')

# Use custom manager methods
recent = TelemetryReading.objects.get_recent(hours=1)
by_channel = TelemetryReading.objects.get_by_channel('NODE3000004')
```

### Validation Pipeline

Use DRF serializers in `core/serializers.py` for all incoming telemetry:

```python
serializer = TelemetrySerializer(data=raw_data)
if serializer.is_valid():
    enriched_data = enrichment_service.enrich(serializer.validated_data)
    repository.save(enriched_data)
else:
    logger.error(f"Validation failed: {serializer.errors}")
```
