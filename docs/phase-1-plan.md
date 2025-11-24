# Phase 1: Django Project Foundation

## Overview

Establish the foundational architecture for the ISS Telemetry system as a Django modular monolith. Focus on project structure, core infrastructure, and development environment.

**Status**: Not Started
**Duration**: 2-3 days
**Prerequisites**: Python 3.14, uv, Docker Desktop

---

## Objectives

1. **Project Structure**: Create modular monolith with 5 independent apps
2. **Data Layer**: Configure TimescaleDB for time-series storage
3. **Background Jobs**: Set up Celery/Beat for async task processing
4. **Core Utilities**: Build reusable base models and helper functions
5. **Development Environment**: Docker Compose for local dependencies
6. **Testing Foundation**: Configure pytest framework

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Django Application                       │
│                  (Modular Monolith - Single Process)        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐  ┌───────────┐  ┌─────────┐  ┌──────────┐     │
│  │   Core   │  │ Storage   │  │Ingestion│  │Processors│     │
│  │(Shared)  │  │(Models)   │  │(Phase 2)│  │(Phase 4) │     │
│  └────┬─────┘  └─────┬─────┘  └────┬────┘  └────┬─────┘     │
│       │              │              │            │          │
│       └──────────────┴──────────────┴────────────┘          │
│                          │                                  │
│                          │ Repository Pattern               │
│                          ▼                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │                                  │
          ▼                                  ▼
    ┌─────────-─┐                      ┌──────────┐
    │TimescaleDB│                      │  Redis   │
    │(Primary DB│                      │(Ephemeral│
    │  + Time-  │                      │  Queue)  │
    │  Series)  │                      └──────────┘
    └─────────-─┘
```

**Key Architectural Decisions**:
- **Settings Split**: Separate base/development/production for environment-specific config
- **Model Ownership**: Each app owns its models; others import (not microservices isolation)
- **Repository Pattern**: Abstract data access layer for testability
- **Single Source of Truth**: TimescaleDB for all data; Redis ephemeral only

---

## Module Structure

```
iss_telemetry_project/
├── config/                    # Django project config
│   ├── settings/
│   │   ├── base.py           # Shared settings
│   │   ├── development.py    # Local dev
│   │   └── production.py     # Deployment
│   ├── celery.py             # Background task config
│   └── urls.py
│
├── apps/                      # All Django apps
│   ├── core/                 # ✓ Phase 1: Base models, utils, serializers
│   ├── telemetry_storage/    # Phase 3: TelemetryReading, TelemetryChannel
│   ├── telemetry_ingestion/  # Phase 2: Lightstreamer client
│   ├── event_processors/     # Phase 4: Analytics (PeeBot)
│   └── dashboards/           # Phase 5: Web UI
│
├── tests/                    # Project-wide tests
├── docker-compose.yml        # Local TimescaleDB + Redis
└── .env                      # Environment config
```

---

## Task Breakdown

### 1. Project Initialization

**Objective**: Bootstrap Django with modular structure and dependency management.

**Tasks**:

1. **Install Dependencies** via uv:
   - Django core: `django`, `djangorestframework`, `django-environ`
   - Database: `psycopg[binary]`, `psycopg[pool]`
   - Background jobs: `celery`, `redis`, `django-celery-beat`
   - Testing: `pytest`, `pytest-django`, `pytest-asyncio`, `model-bakery`
   - Code quality: `ruff`, `mypy`, `django-stubs`

2. **Initialize Django Project**:
   - Use `config/` as project root (not default `project_name/`)
   - Split settings into `base.py`, `development.py`, `production.py`
   - Auto-load settings based on `DJANGO_ENV` environment variable
   - Configure `django-environ` for .env file support

3. **Scaffold 5 Apps**:
   - Create `apps/` directory for all Django apps
   - Generate apps: core, telemetry_storage, telemetry_ingestion, event_processors, dashboards
   - Add to `INSTALLED_APPS` with full path: `apps.core`, `apps.telemetry_storage`, etc.

4. **Environment Configuration**:
   - Create `.env.example` with all required variables
   - Create `.env` for local development (not committed)
   - Key variables: `DJANGO_ENV`, `SECRET_KEY`, `DATABASE_URL`, `CELERY_BROKER_URL`

**Critical Points**:
- Use `apps.app_name` pattern in `INSTALLED_APPS`
- TimescaleDB connection string: `postgresql://user:pass@host:port/db_name`
- Set `USE_TZ=True` for proper timezone handling

**Verification**:
- [x] Django project runs: `uv run python manage.py runserver`
- [x] Settings load correctly for each environment
- [x] All 5 apps recognized by Django

---

### 2. Database Setup - TimescaleDB

**Objective**: Configure PostgreSQL with TimescaleDB extension for time-series data.

**Tasks**:

1. **Docker Compose Configuration**:
   - Service 1: `timescaledb` (postgres:15 + timescale extension)
   - Service 2: `redis` (for Celery)
   - Volume mounting for data persistence
   - Health checks for both services
   - Initialization script to enable TimescaleDB extension

2. **Django Database Config**:
   - Use `django-environ` to parse `DATABASE_URL`
   - Enable connection pooling
   - Configure timeout settings for production
   - Separate test database configuration

**Docker Compose Structure**:
```yaml
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    volumes: init-timescale.sql (creates extension)

  redis:
    image: redis:7-alpine
```

**Critical Points**:
- TimescaleDB extension must be created: `CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE`
- Test database should use separate name to avoid conflicts
- Connection pooling reduces overhead for high-throughput scenarios

**Verification**:
- [x] Docker containers start successfully
- [x] TimescaleDB extension installed: check with `SELECT * FROM pg_extension`
- [x] Django connects to database: `manage.py dbshell`
- [x] Redis accessible: `redis-cli ping`

---

### 3. Core Module Implementation

**Objective**: Build shared utilities, base models, and common functionality.

**Components to Implement**:

#### 3.1 Abstract Base Models

Create reusable Django abstract models in `apps/core/models.py`:

1. **TimeStampedModel**:
   - Fields: `created_at`, `updated_at`
   - Auto-populated via `auto_now_add` and `auto_now`
   - Indexed for querying by creation/modification time

2. **UUIDModel**:
   - Primary key: `id = UUIDField(default=uuid4)`
   - Use when natural keys don't exist
   - Better for distributed systems (no collisions)

3. **SoftDeleteModel**:
   - Field: `deleted_at` (nullable datetime)
   - Methods: `soft_delete()`, `restore()`, `is_deleted` property
   - Custom managers: `SoftDeleteManager` (excludes deleted), `AllObjectsManager` (includes all)

**Usage Pattern**:
```python
class MyModel(TimeStampedModel, SoftDeleteModel):
    # Inherits created_at, updated_at, deleted_at
    pass
```

#### 3.2 Utility Functions

Create helpers in `apps/core/utils.py`:

1. **generate_event_id()**: Creates UUID4 for unique event tracking
2. **normalize_timestamp()**: Converts Unix/ISO/datetime to timezone-aware datetime
3. **safe_decimal()**: Safely converts values to Decimal with fallback
4. **chunk_list()**: Splits lists for batch processing

**Purpose**: Centralize common operations used across all phases.

#### 3.3 Exception Classes

Define hierarchy in `apps/core/exceptions.py`:
- `TelemetryError` (base)
- `ValidationError`, `EnrichmentError`, `IngestionError`
- `ProcessorError`, `ExternalServiceError`

**Purpose**: Consistent error handling and logging across modules.

#### 3.4 DRF Serializers (Placeholder)

Create `apps/core/serializers.py`:
- `BaseTelemetrySerializer` (empty for now)
- Full implementation in Phase 2 when ingestion begins

**Critical Points**:
- All models should be abstract (no database tables in core)
- Utils should be pure functions (no side effects)
- Follow Django best practices for model mixins

**Verification**:
- [ ] Import base models: `from apps.core.models import TimeStampedModel`
- [ ] Run utility function tests
- [ ] No migrations created for core app (all abstract)

---

### 4. Celery Configuration

**Objective**: Set up distributed task queue for background processing.

**Flow Diagram**:
```
Django App                    Celery Workers              Redis
   │                               │                        │
   │──── task.delay() ───────────>│                        │
   │                               │──── enqueue ─────────>│
   │                               │                        │
   │                               │<──── dequeue ──────────│
   │                               │                        │
   │                               │ (execute task)         │
   │                               │                        │
   │<──── result (optional) ───────│──── store result ────>│
```

**Tasks**:

1. **Create Celery App** (`config/celery.py`):
   - Initialize Celery instance
   - Auto-discover tasks from all installed apps
   - Configure JSON serialization (not pickle)
   - Set timezone to UTC

2. **Configure Celery Beat Schedule**:
   - Add test periodic task (every 60s)
   - Placeholder for future analytics tasks (Phase 4)
   - Use database-backed schedule with `django-celery-beat`

3. **Create Test Task** (`apps/core/tasks.py`):
   - Simple `@shared_task` that logs message
   - Verifies Celery setup works end-to-end

4. **Django Integration** (`config/__init__.py`):
   - Import celery app when Django starts
   - Ensures tasks are registered before use

**Critical Points**:
- Use Redis as broker AND result backend (same instance)
- Enable `task_track_started=True` for better monitoring
- Configure retry logic: `autoretry_for`, `retry_kwargs`

**Verification**:
- [ ] Start Celery worker: `celery -A config worker`
- [ ] Start Celery Beat: `celery -A config beat`
- [ ] Test task executes every 60 seconds
- [ ] Manual task execution: `task.delay()` returns AsyncResult

---

### 5. App Scaffolding

**Objective**: Create directory structure for all 5 apps (implementation in later phases).

**Per-App Structure**:

```
apps/telemetry_storage/
├── models.py              # Data models (Phase 3)
├── repositories.py        # Data access layer (Phase 3)
├── managers.py            # Custom QuerySet managers (Phase 3)
└── migrations/

apps/telemetry_ingestion/
├── services/
│   ├── lightstreamer_client.py   # (Phase 2)
│   ├── validator.py              # (Phase 2)
│   └── enricher.py               # (Phase 2)
├── views.py               # REST API endpoints (Phase 2)
└── management/commands/
    └── run_lightstreamer.py      # (Phase 2)

apps/event_processors/
├── models.py              # DetectedEvent, ProcessorState (Phase 4)
├── processors/
│   ├── base.py            # BaseProcessor class (Phase 4)
│   └── pee_bot.py         # PeeBot detector (Phase 4)
├── services/
│   ├── twitter_client.py  # (Phase 4)
│   └── joke_generator.py  # (Phase 4)
└── tasks.py               # Celery periodic tasks (Phase 4)

apps/dashboards/
├── views.py               # HTTP views (Phase 5)
├── consumers.py           # WebSocket consumers (Phase 5)
├── templates/dashboards/
└── static/dashboards/
```

**Tasks**:
- Create directory structure for each app
- Add placeholder files with docstrings indicating phase
- Ensure all apps have `apps.py` with proper `AppConfig`

**Critical Points**:
- Don't implement functionality yet - this is scaffolding only
- Add comments like "# TODO: Phase 3" to indicate future work
- Keep models.py files but leave models undefined

**Verification**:
- [ ] All apps recognized: `manage.py check`
- [ ] No migration errors for empty apps
- [ ] Directory structure matches plan

---

### 6. Initial Migrations & Admin

**Objective**: Apply Django's built-in migrations and set up admin interface.

**Tasks**:

1. **Run Initial Migrations**:
   - Django auth, sessions, contenttypes, admin
   - django-celery-beat (for periodic task management)
   - No custom app migrations yet (core is abstract, others empty)

2. **Create Superuser**:
   - For admin access during development
   - Credentials stored securely (not in code)

3. **Verify Admin Interface**:
   - Access `/admin/`
   - Check django-celery-beat models visible (Periodic Tasks, etc.)

**Verification**:
- [ ] Migrations apply cleanly: `manage.py migrate`
- [ ] Database tables created (check with `\dt` in psql)
- [ ] Admin login works
- [ ] No migration warnings

---

### 7. Testing Framework

**Objective**: Configure pytest for Django with async support and coverage.

**Configuration**:

1. **pytest.ini**:
   - Django settings module: `config.settings`
   - Test discovery patterns
   - Coverage reporting (terminal + HTML)
   - Async mode: auto
   - Reuse DB for speed (`--reuse-db`)

2. **conftest.py**:
   - Fixture for database setup
   - Separate test database name
   - Mock fixtures for future use

3. **Example Tests** (`tests/test_core_utils.py`):
   - Test `generate_event_id()` returns valid UUID
   - Test `normalize_timestamp()` handles all input types
   - Test `safe_decimal()` conversion and fallback
   - Test `chunk_list()` splits correctly

**Test Execution Flow**:
```
pytest discovers tests/
  → conftest.py creates fixtures
    → test_*.py files execute
      → Coverage measured
        → HTML report generated
```

**Critical Points**:
- Use `--reuse-db` for fast test iterations (don't recreate DB each time)
- Use `--nomigrations` if models don't change (faster)
- Separate test database to avoid polluting dev data

**Verification**:
- [ ] `uv run pytest` executes successfully
- [ ] All example tests pass
- [ ] Coverage report shows core utils covered
- [ ] HTML coverage report generated in `htmlcov/`

---

### 8. Git & Documentation

**Objective**: Initialize version control and document Phase 1 completion.

**Tasks**:

1. **Git Configuration**:
   - Initialize repo: `git init`
   - Create `.gitignore` (Python, Django, env files, IDE files)
   - Verify sensitive files excluded (`.env`, `*.pyc`, `__pycache__/`)

2. **Initial Commit**:
   - Commit message describing Phase 1 completion
   - Include all scaffolded apps and configuration

3. **Update README**:
   - Add project overview
   - Link to architecture document
   - Add setup instructions for new developers

**Verification**:
- [ ] Git repository initialized
- [ ] `.env` not tracked (in .gitignore)
- [ ] Initial commit created
- [ ] README reflects current state

---

## Success Criteria

Phase 1 is complete when:

- ✅ Django development server runs without errors
- ✅ TimescaleDB connection established and migrations apply
- ✅ All 5 Django apps scaffolded with correct structure
- ✅ Celery worker and Beat scheduler functional
- ✅ Core base models and utilities implemented
- ✅ Docker Compose brings up TimescaleDB + Redis
- ✅ pytest test suite runs and passes
- ✅ Django admin accessible and functional
- ✅ Git repository initialized with initial commit

---

## Dependency Graph

```
Task Dependencies:

1. Install Dependencies
   ↓
2. Initialize Project Structure
   ↓
3. Configure Settings ──────┐
   ↓                        │
4. Docker Compose Setup     │
   ↓                        │
5. Database Config ─────────┘
   ↓
6. Core Module Implementation
   ↓
7. Celery Configuration
   ↓
8. App Scaffolding
   ↓
9. Initial Migrations
   ↓
10. Testing Framework
    ↓
11. Git Setup
```

**Parallel Execution Opportunities**:
- Tasks 3-4 can run in parallel (settings + docker)
- Tasks 6-7 can run in parallel (core + celery)
- Task 10 can start once task 6 is complete

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| TimescaleDB extension fails to install | High | Use official Docker image; verify extension in init script |
| Settings import errors | Medium | Test each settings file independently; use linter |
| Celery connection issues | Medium | Verify Redis running; test with simple task first |
| App import problems | Low | Use `apps.` prefix consistently; check INSTALLED_APPS |

---

## Next Steps

After Phase 1 completion:

1. **Phase 2**: Implement Telemetry Ingestion
   - Lightstreamer client connection
   - DRF serializers for validation
   - Enrichment service
   - Repository pattern for database writes

2. **Documentation Updates**:
   - Document any deviations from plan
   - Add troubleshooting notes
   - Update README with actual setup steps

---

## Quick Reference

**Essential Commands**:
```bash
# Start development environment
docker-compose up -d
uv run python manage.py runserver

# Run Celery (separate terminals)
uv run celery -A config worker --loglevel=info
uv run celery -A config beat --loglevel=info

# Testing
uv run pytest
uv run pytest --cov=apps

# Database
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py dbshell
```

**Key Files**:
- Config: `config/settings/base.py`
- Environment: `.env`
- Dependencies: `pyproject.toml`
- Docker: `docker-compose.yml`
- Tests: `pytest.ini`, `tests/conftest.py`
