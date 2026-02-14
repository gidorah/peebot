# PEEBOT KNOWLEDGE BASE

**Generated:** 2026-01-02
**Architecture:** Django Modular Monolith (TimescaleDB)
**State:** INGESTION_READY (Ingestion pipeline verified, Validation & Enrichment active)

## OVERVIEW
PeeBot is a modular monolith for ISS telemetry analytics. It ingests real-time data from Lightstreamer, stores it in TimescaleDB (`TelemetryReading`), and uses polling-based analytics to detect events (e.g., UPA activity) and trigger actions (tweets).

**Key Tech**: Python 3.14+, Django 5.2, TimescaleDB, Celery/Redis, Seq (Logging), `uv` (pkg manager), `just` (runner), Pydantic (Validation).

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
    - **Bridge**: `LightstreamerClient` (Sync) → `asyncio.Queue` → Consumer Task → `abulk_create`.
4.  **Analytics Pattern**:
    - **Polling**: Celery Beat triggers tasks. No signals.
    - **Sliding Window**: Query `TelemetryReading` for last N minutes.
5.  **Tooling**:
    - **`uv`**: ALWAYS use `uv run`, `uv sync`.
    - **`ruff`**: No linting workarounds. Fix the root cause.
    - **`mypy`**: Strict mode enabled.
6.  **Code Style**:
    - MUST follow guidelines in `docs/code_styleguides/python.md`.
7.  **Temporary Artifacts**:
    - MUST use `_work-tmp/` for temporary scripts, logs, or intermediate docs.
    - These files are ephemeral and will be deleted at the end of the session.
8.  **Testing**:
    - ALWAYS use `just test` (or `just test-pooled`) for running tests.
    - NEVER run `pytest` directly - the Justfile ensures proper environment setup (Docker, DB, etc.).

## DEV COMMANDS
```bash
just dev-up        # Start full stack (Docker + Seq + Ingestion)
just dev-down      # Stop stack
just test          # Run tests (pytest)
just test-pooled   # Run tests with pgbouncer (pytest)
uv run python manage.py runserver # Dev server (Logs to Console + Seq)
uv run python manage.py run_lightstreamer # Ingestion (Manual run)
# Seq Dashboard: http://localhost:5341 (admin/password)
```

## SECURITY & CONFIG
- **Secrets**: `userlist.txt` passwords must match `.env`.
- **PgBouncer**: Internal port `6432`. Hybrid Auth.
- **Git**: Use `/commit` command. Never commit `.env`.

---
# Spec-Driven Development (SDD) Protocol

## 1. Documentation Structure
All agents must adhere to the following folder hierarchy:

### `/docs/incoming` (Source of Truth)
- **Purpose:** Contains raw materials (customer chats, PRDs, design mocks).
- **Rule:** Agents read from here but NEVER modify files here.

### `/docs/system-solution` (The Brain)
- **Purpose:** AI-generated high-level plans.
- **Rule:** Before writing code, the system architecture, stack, and high-level requirements must be defined here.
- **Key File:** `main-tasks.md` acts as the project roadmap.
- **Decision Log:** `tech-decisions.md` must track every important technical/architectural decision.

### `/docs/implementation` (The Hands)
- **Purpose:** Execution of specific features.
- **Structure:** One folder per task ID (e.g., `T001 - User Auth`).
- **Workflow:**
  1. Create folder `T### - Name`.
  2. Create `requirements.md` (What are we building?).
  3. Create `design.md` (How are we building it?).
  4. Create `tasks.md` (Checklist of coding steps).
  5. Only THEN generate code.

## 2. SDD Workflow Phases
Agents must follow these phases sequentially:

### Phase 1: System Solution
- Define high-level requirements and architecture in `/docs/system-solution`.
- Decompose the project into sequential epics in `main-tasks.md`.

### Phase 2: Spec Generation
- For each task in `main-tasks.md`, create a dedicated implementation folder.
- Generate `requirements.md`, `design.md`, and `tasks.md` BEFORE writing code.

### Phase 3: Controlled Execution
- Implement code ONE task at a time from `tasks.md`.
- Generate tests to validate the implementation.

### Phase 4: Documentation Review
- Update project documentation (README, architecture, etc.) after task completion to ensure it reflects the true state of the code.

## 3. The Golden Rule
**"Doc-First, Code-Later."**
No code is written until the implementation documentation for that specific task is complete and verified against the `/docs/system-solution` directives.
