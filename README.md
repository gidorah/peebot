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
|   |   |-- services/              # Twitter client, joke generator
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
- **Tweepy** - Twitter API integration

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
[Validation Service] <- DRF Serializers
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
[External Actions] <- Twitter, Email, etc.
```

### Polling Architecture

Analytics modules use a **polling pattern**:

1. Celery Beat triggers periodic task (e.g., every 30 seconds)
2. Query `ProcessorState` for `last_processed_at` timestamp
3. Query `TelemetryReading` for new data since last check
4. Analyze sliding window (e.g., last 10 minutes)
5. Detect events and store results in `DetectedEvent`
6. Update `ProcessorState` with current timestamp

## Database Schema

### TelemetryReading (TimescaleDB Hypertable)

Stores individual telemetry readings with time-based partitioning:

- `id`: BigAutoField
- `channel`: ForeignKey -> TelemetryChannel
- `timestamp`: DateTimeField (indexed)
- `value`: DecimalField
- `calibrated_data`: DecimalField
- `event_id`: UUIDField (unique)
- `ingested_at`: DateTimeField
- `metadata`: JSONField

**Optimizations**:
- Automatic time partitioning (1-day chunks)
- Automatic compression after 7 days
- Retention policy: drop chunks > 30 days
- Primary index: `(channel, timestamp DESC)`

### TelemetryChannel

Metadata for ~400 ISS telemetry channels:

- `id`: AutoField
- `item_id`: CharField (unique, e.g., "NODE3000004")
- `description`: TextField
- `module_name`: CharField
- `unit`: CharField
- `is_active`: BooleanField
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
- `last_processed_at`: DateTimeField
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
