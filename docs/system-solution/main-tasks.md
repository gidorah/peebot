# Project Roadmap: PeeBot System

**Status**: Production deployed. Follow-up hardening and CI work continue in implementation tasks.

## Refactoring Tasks (Priority)

These tasks address architectural changes and bugs in the **currently implemented** code (`apps/core` and `apps/telemetry_storage`).

- [x] **Refactor (Storage)**: Update `TelemetryReading` unique constraint.
    - *Goal*: Change from `(id, timestamp)` to `(channel, timestamp)` for deterministic deduplication.
    - *Files*: `apps/telemetry_storage/models.py`.
    - **Completion Date**: 2026-02-18 (T004 — Phases 1–3 complete)

- [x] **Fix (Core)**: Resolve `timezone.datetime` attribute error.
    - *Goal*: Replace incorrect `timezone.datetime` usage with `timezone.now()` or `datetime` module.
    - *Files*: `apps/core/models.py`.

- [x] **Fix (Core)**: Resolve `deleted_at` field obscuration.
    - *Goal*: Fix duplicate/conflicting field definitions in base models.
    - *Files*: `apps/core/models.py`.

- [x] **Fix (Storage)**: Resolve `Meta` class inheritance conflicts.
    - *Goal*: Ensure `TelemetryReading.Meta` correctly overrides/inherits from base model Meta classes to satisfy MRO.
    - *Files*: `apps/telemetry_storage/models.py`.

## Phase 2: Ingestion Implementation

- [x] **Implement (Ingestion)**: Create Enrichment Service (`enricher.py`).
    - *Goal*: Move timestamp normalization and year-rollover logic from management command to a dedicated service.
    - *Files*: `apps/telemetry_ingestion/services/enricher.py`.

- [x] **Refactor (Ingestion)**: Update Validation Layer (Pydantic).
    - *Goal*: Replace DRF Serializer with Pydantic model for high-performance ingestion (ADR-004). Integrate into `run_lightstreamer` loop.
    - *Files*: `apps/telemetry_ingestion/services/validator.py`, `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`.

## Phase 3: Event Processing Implementation (T003)

- [x] **T003-1 (Setup)**: Create `event_processors` Django app and register in settings.
- [x] **T003-2 (Models)**: Implement `ProcessorState`, `DetectedEvent`, and `SocialPost` models.
- [x] **T003-3 (Base Processor)**: Implement `BaseProcessor` abstract class with jitter utility.
- [x] **T003-4 (PeeBot)**: Implement `PeeBotProcessor` with burst detection algorithm.
- [x] **T003-5 (Services)**: Implement `JokeGenerator` and `BlueskyClient` services.
- [x] **T003-6 (Celery)**: Implement Celery task and Beat schedule (30s interval).
- [x] **T003-7 (Testing)**: Unit tests for processor logic, integration test for full flow.
- **T003 Completion Date**: 2026-02-06

## Phase 4: Production Deployment (T005)

- [x] **T005-1 (Dockerfile)**: Write multi-stage production Dockerfile with baked dependencies, non-root user, and entrypoint script.
    - [x] Step 1: Multi-stage Dockerfile (`docker/prod/Dockerfile`) — builder + runtime stages, `/opt/venv`, `DJANGO_SETTINGS_MODULE`.
    - [x] Step 2: Non-root `python` user (UID/GID 1000), `chown /workspace`.
    - [x] Step 3: Entrypoint script (`/usr/local/bin/entrypoint.sh`) — `collectstatic --noinput` then `exec "$@"`, `CMD ["gunicorn", ...]`.
    - [x] Step 4: Verify `.dockerignore` excludes `.env`, `.git/`, `docs/`, `_work-tmp/`, `.venv/`, caches, logs.
- [x] **T005-2 (Settings)**: Harden `config/settings/production.py` — stdout logging, proxy SSL trust, CSRF origins.
    - [x] Step 5: Replace `LOGGING` dict with stdout-only `console` handler, remove `file` handler and `logs/django.log`.
    - [x] Step 6: `SECURE_SSL_REDIRECT = False`, add `SECURE_PROXY_SSL_HEADER` for Traefik trust.
    - [x] Step 7: `CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])`.
    - [x] Step 8: Confirm `STATIC_ROOT` and `STATIC_URL` set correctly.
    - [x] Step 8a: Add WhiteNoise — `pyproject.toml` dep, `WhiteNoiseMiddleware` after `SecurityMiddleware`, `CompressedManifestStaticFilesStorage`.
    - [x] Step 9: Verify `django_structlog` / Seq absent from production `INSTALLED_APPS`.
- [x] **T005-3 (DB Init)**: Parameterize `init-timescale.sql` password via shell wrapper (`init-timescale.sh`).
    - [x] Step 10: Create `docker/scripts/init-timescale.sh` — `set -euo pipefail`, env var validation, single-quote escaping, `psql` heredoc with TimescaleDB extension + `pgbouncer_auth` role.
    - [x] Step 11: Update prod compose TimescaleDB to mount `init-timescale.sh` and pass `PGBOUNCER_AUTH_PASSWORD`.
- [x] **T005-4 (PgBouncer)**: Resize production PgBouncer pools for 4vCPU/8GB VPS, disable internal TLS.
    - [x] Step 12: Disable TLS (`client_tls_sslmode = disable`, `server_tls_sslmode = disable`) in `pgbouncer.ini`.
    - [x] Step 13: Resize pools — `default_pool_size=10`, `min_pool_size=3`, `reserve_pool_size=5`, `max_client_conn=50`, `max_db_connections=20`.
    - [x] Step 14: Create `docker/prod/pgbouncer/entrypoint.sh` — generates `userlist.txt` at runtime from `PGBOUNCER_AUTH_PASSWORD`.
    - [x] Step 14a: Update prod compose PgBouncer — remove `userlist.txt` mount, add entrypoint script mount, `entrypoint:`, `command:`, env var.
- [x] **T005-5 (Compose)**: Rewrite `docker/prod/docker-compose.yml` — baked images, add ingestion, remove Daphne, conservative resources, no external infra ports.
    - [x] Step 15: Remove source code volume mounts (`../../:/workspace`) and `uv_cache` from all app services.
    - [x] Step 16: Remove `uv sync --frozen &&` prefix from all `command:` directives.
    - [x] Step 17: Add `ingestion` service (`python manage.py run_lightstreamer`, same image, 512M/0.5 CPU).
    - [x] Step 18: Remove Daphne service and port 8001 mapping.
    - [x] Step 19: Remove `env_file` directives from all services (Coolify injects env vars directly).
    - [x] Step 20: Resize resource limits, apply TimescaleDB tuning via `command: postgres -c` flags, 3 Gunicorn workers, Redis 256MB.
    - [x] Step 21: Remove external port exposure from TimescaleDB, PgBouncer, Redis — only `web:8000` mapped to host.
- [x] **T005-6 (Env Docs)**: Create `.env.production.example` and Coolify setup guide.
    - [x] Step 22: Create `.env.production.example` — all required vars with descriptions, placeholder values, generation commands.
    - [x] Step 23: Create `docs/implementation/T005 - Production Deployment/coolify-setup.md` — step-by-step Coolify project configuration guide.
- [x] **T005-7 (Pipeline)**: Add production Justfile recipes and first-time deployment runbook.
    - [x] Step 24: Add `prod-build`, `prod-migrate`, `prod-shell`, `prod-seed`, `prod-logs` recipes to `Justfile`.
    - [x] Step 25: Verify design.md Section 9 runbook covers env setup → deploy → healthchecks → migrate → seed → superuser → ingestion/Celery verification.
- [x] **T005-8 (ADRs)**: Record ADR-012 (Baked Images), ADR-013 (Stdout Logging), ADR-014 (Coolify Deployment).
    - [x] Step 26: Update `docs/system-solution/main-tasks.md` with detailed T005 step entries (this update).
    - [x] Step 27: Add ADR-012, ADR-013, ADR-014 to `docs/system-solution/tech-decisions.md`.

## Phase 5: Production Hardening (T006)

- [ ] **T006-1 (Health Checks)**: Add `/healthz` and `/readyz` endpoints plus production container health checks.
- [ ] **T006-2 (Test Hygiene)**: Remove pytest collection and asyncio warnings from the existing suite.
- [ ] **T006-3 (REST API Foundation)**: Add read-only API endpoints for channels and detected events.
- [ ] **T006-4 (Manual Injection)**: Add a debug-only telemetry injection endpoint for testing and operational verification.
- [ ] **T006-5 (OpenAPI Docs)**: Add schema generation and Swagger UI.

## Phase 6: Pull Request Test CI (T007)

- [x] **T007-1 (Workflow)**: Add a GitHub Actions workflow that runs on PR open, synchronize, and reopen events targeting `main`.
- [x] **T007-2 (Database Service)**: Run tests against a TimescaleDB service container with direct test DB access.
- [x] **T007-3 (Test Entrypoint Alignment)**: Keep `just test` as the canonical test command while allowing CI to provide its own `DOTENV_PATH`.
- [x] **T007-4 (Repo Docs)**: Document the PR CI behavior and local reproduction path in repository docs.

## Phase 7: Quality CI (T008)

- [x] **T008-1 (Workflow)**: Add a GitHub Actions workflow that runs Ruff and mypy on PR open, synchronize, and reopen events targeting `main`.
- [x] **T008-2 (Check Separation)**: Expose separate `ruff` and `mypy` check names for branch protection and easier diagnosis.
- [x] **T008-3 (Repo Docs)**: Document the PR quality checks and local reproduction commands in repository docs.

## Phase 8: Operational Noise Hardening (T009)

- [ ] **T009-1 (Ingestion Sentry Noise)**: Treat transient `OperationalError` in `run_lightstreamer.flush_buffer()` as a retryable warning while still closing stale DB connections.
    - *Goal*: Prevent routine ingestion DB disconnects from creating Sentry issues via `LoggingIntegration(event_level=ERROR)`.
    - *Files*: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`, `apps/telemetry_ingestion/tests/test_run_lightstreamer_command.py`.
