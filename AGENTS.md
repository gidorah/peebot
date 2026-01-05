# PEEBOT KNOWLEDGE BASE

**Generated:** 2026-01-02
**Architecture:** Django Modular Monolith (TimescaleDB)
**State:** STORAGE_READY (Storage layer verified, Ingestion pending)

## OVERVIEW
PeeBot is a modular monolith for ISS telemetry analytics. It ingests real-time data from Lightstreamer, stores it in TimescaleDB (`TelemetryReading`), and uses polling-based analytics to detect events (e.g., UPA activity) and trigger actions (tweets).

**Key Tech**: Python 3.14+, Django 5.2, TimescaleDB, Celery/Redis, `uv` (pkg manager), `just` (runner).

## STRUCTURE
```
peebot/
├── apps/                  # DOMAIN MODULES (Strict Boundaries)
│   ├── core/              # Shared utils, BaseModels (TimeStamped, UUID)
│   ├── telemetry_storage/ # OWNS Data (Readings, Channels). Repository Pattern.
│   ├── telemetry_ingestion/# Ingestion Service. NO Models. Imports from storage.
│   ├── event_processors/  # Analytics Logic. OWNS DetectedEvent. Polling tasks.
│   └── dashboards/        # UI/WebSockets. Reads all, owns none.
├── config/                # Django Settings (Base, Dev, Prod)
├── docker/                # Infrastructure (PgBouncer, Timescale, Redis)
└── Justfile               # Task runner definitions
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| **Core Logic** | `apps/core` | Base classes, shared utils |
| **Storage** | `apps/telemetry_storage` | DB Models, Repositories |
| **Ingestion** | `apps/telemetry_ingestion` | Lightstreamer client, Validation |
| **Analytics** | `apps/event_processors` | Event detection, Polling tasks |
| **UI** | `apps/dashboards` | Frontend, WebSockets |

## STRICT LAWS (NON-NEGOTIABLE)
1.  **Module Ownership**:
    - `telemetry_ingestion` MUST NOT define models. It imports from `telemetry_storage`.
    - `event_processors` OWNS `DetectedEvent`.
    - `telemetry_storage` OWNS `TelemetryReading`.
2.  **Data Access**:
    - Use `apps.telemetry_storage.repositories` for DB ops (Future).
    - Ingestion MUST use Async ORM / Bulk creates.
3.  **Ingestion Pattern**:
    - **Bridge**: `LightstreamerClient` (Sync) → `asyncio.run_coroutine_threadsafe` → Django Async.
4.  **Analytics Pattern**:
    - **Polling**: Celery Beat triggers tasks. No signals.
    - **Sliding Window**: Query `TelemetryReading` for last N minutes.
5.  **Tooling**:
    - **`uv`**: ALWAYS use `uv run`, `uv sync`.
    - **`ruff`**: No linting workarounds. Fix the root cause.
    - **`mypy`**: Strict mode enabled.

## DEV COMMANDS
```bash
just dev-up        # Start full stack (Docker)
just dev-down      # Stop stack
just test          # Run tests (pytest)
uv run python manage.py runserver # Dev server
uv run python manage.py run_lightstreamer # Ingestion
```

## CURRENT STATE (SCAFFOLDING)
- **Infrastructure**: CI/CD, Docker, PgBouncer, Linting are ACTIVE.
- **Ingestion**: Lightstreamer client connected. Validation/Storage pending.
- **Storage**: Models (`TelemetryReading`) are DEFINED IN DOCS but EMPTY in code.
- **Processors**: Analytics logic (`PeeBot`) is DEFINED IN DOCS but EMPTY in code.

## SECURITY & CONFIG
- **Secrets**: `userlist.txt` passwords must match `.env`.
- **PgBouncer**: Internal port `6432`. Hybrid Auth.
- **Git**: Use `/commit` command. Never commit `.env`.
