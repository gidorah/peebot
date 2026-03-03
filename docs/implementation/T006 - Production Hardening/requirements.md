# Requirements: T006 — Production Hardening

## 1. Goal

Harden the production-deployed PeeBot system with health check endpoints, test hygiene fixes, a DRF REST API foundation, a manual telemetry injection endpoint, and self-documenting OpenAPI/Swagger docs. This phase resolves all remaining Architecture §9.2 monitoring gaps, outstanding code hygiene issues, and FR-ING-006 (REST injection).

## 2. Background

The core pipeline (ingestion → storage → event detection → Bluesky posting) is fully operational in production (T001–T005). Sentry observability (error tracking, logs, Celery Crons, custom metrics) is integrated. **135 tests pass.** However, several production readiness gaps remain:

1. **No health check endpoints** — The `web` service in `docker/prod/docker-compose.yml` has no `healthcheck` directive. Coolify/Traefik cannot determine if Django is ready to serve traffic, leading to potential routing to unready containers during restarts.
2. **8 `PytestCollectionWarning`** — Test-specific processor subclasses in `test_base_processor.py` (lines 77–119) are named `TestProcessor*`, which pytest collects as test classes. They fail collection because `ConcreteProcessor.__init__` takes arguments.
3. **2 spurious `@pytest.mark.asyncio`** — Two sync tests (`test_get_confidence_returns_decimal` L344, `test_get_confidence_zero_for_empty` L354) are marked async but are plain `def` functions.
4. **No REST API** — `djangorestframework` is installed and in `INSTALLED_APPS`, but no URL routes, routers, or viewsets exist. The system has no programmatic data access surface.
5. **No manual injection endpoint** — FR-ING-006 specifies a REST endpoint for manual telemetry submission, useful for testing and operational debugging.
6. **No API documentation** — No OpenAPI/Swagger interface exists for API discoverability.

## 3. Functional Requirements

### 3.1 Health Check Endpoints (FR-T006-001)

1. The system shall expose a `GET /healthz` endpoint that returns HTTP 200 with `{"status": "ok"}` when the Django process is running (liveness probe).
2. The system shall expose a `GET /readyz` endpoint that returns HTTP 200 with `{"status": "ready", "checks": {...}}` when both the database (via a lightweight `SELECT 1` query) and Redis (via `PING`) are reachable. If either dependency is unreachable, the endpoint shall return HTTP 503 with details of the failing check(s).
3. Both endpoints shall not require authentication.
4. Both endpoints shall be defined in `apps/core/views.py` (or a dedicated `apps/core/health.py` module) and wired into `config/urls.py` at the root level (not under `/api/`).
5. The `web` service in `docker/prod/docker-compose.yml` shall include a `healthcheck` directive against `/healthz` with appropriate intervals and retries. Since the production image does not include `curl` or `wget` (only `libpq5` is installed), the healthcheck command shall use Python's `urllib` (e.g., `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"`).

### 3.2 Fix Pytest Warnings (FR-T006-002)

1. The 8 test-specific processor subclasses in `apps/event_processors/tests/test_base_processor.py` (lines 77–119) shall be renamed to not start with `Test` so pytest does not attempt to collect them as test classes. The `PytestCollectionWarning` warnings shall be eliminated.
2. The 2 `@pytest.mark.asyncio` decorators on sync test methods (`test_get_confidence_returns_decimal` and `test_get_confidence_zero_for_empty`) shall be removed.
3. After fixes, `just test` shall produce **0 `PytestCollectionWarning`** and **0 `PytestWarning`** related to asyncio marks on sync functions.

### 3.3 REST API Skeleton (FR-T006-003)

1. The system shall expose a versioned REST API under the URL namespace `api/v1/`.
2. A new `config/api_urls.py` module shall define a DRF `DefaultRouter` and register viewsets.
3. `config/urls.py` shall include `api/v1/` pointing to `config/api_urls.py` via `include()`.
4. The system shall expose `GET /api/v1/channels/` — a read-only, paginated list of all `TelemetryChannel` records (fields: `id`, `public_pui`, `description`, `ops_nom`, `eng_nom`, `unit`).
5. The system shall expose `GET /api/v1/events/` — a read-only, paginated list of `DetectedEvent` records (fields: `id`, `event_type`, `channel_id`, `detected_at`, `confidence`, `metadata`, `created_at`), ordered by `-detected_at`.
6. Pagination shall use DRF's `PageNumberPagination` with a default page size of 50. A `REST_FRAMEWORK` configuration dict shall be added to `config/settings/base.py` with the default pagination class, page size, and default permission settings.
7. All list endpoints shall be read-only (`ModelViewSet` with `list` and `retrieve` actions only, or `ReadOnlyModelViewSet`).
8. Serializers shall be defined in their respective app modules (`apps/telemetry_storage/serializers.py`, `apps/event_processors/serializers.py`).
9. The per-channel readings endpoint (`GET /api/v1/channels/{id}/readings/`) specified in System Overview §Communication is **out of scope** for T006 — deferred to T007 (Dashboard Foundation) where it serves as a chart data source.

### 3.4 Manual Injection Endpoint (FR-T006-004)

1. The system shall expose `POST /api/v1/telemetry/inject/` for manual telemetry submission.
2. The endpoint shall accept a JSON body with fields: `pui` (channel PUI string, required), `timestamp` (ISO 8601 UTC datetime string, required), `value` (decimal number, required), and optional metadata fields (`calibrated_data`, `status_class`, `status_indicator`, `status_color`). The endpoint shall accept **standard ISO 8601 timestamps** (not the Lightstreamer ISS hours-from-SOY format), making it suitable for manual/debugging use.
3. The endpoint shall reuse the existing ingestion pipeline where applicable: Pydantic validation (`validator.py`) for field-level validation, enrichment (`enricher.py`) for data normalization, and repository persistence (`DjangoTelemetryRepository.create_reading`). **PUI resolution**: the endpoint shall resolve the submitted PUI string to a `TelemetryChannel` model instance via `TelemetryChannel.objects.get(public_pui=pui)`. If the PUI is not found, the endpoint shall return HTTP 404 with an error message. Note: the existing enricher's SOY-to-UTC timestamp conversion shall be bypassed since the endpoint accepts ISO 8601 directly — a thin adapter or a dedicated injection Pydantic model may be needed (deferred to design).
4. The endpoint shall be restricted to non-production use:
   - When `DEBUG=True`: accessible without authentication.
   - When `DEBUG=False`: the endpoint shall return HTTP 403 Forbidden, OR require a valid API key via a custom DRF permission class (implementation choice deferred to design).
5. On success, the endpoint shall return HTTP 201 with the created reading's serialized data.
6. On validation failure, the endpoint shall return HTTP 400 with Pydantic validation error details.

### 3.5 OpenAPI Documentation (FR-T006-005)

1. The system shall generate an OpenAPI 3.0 schema from the DRF viewsets and serializers.
2. The system shall expose an interactive Swagger UI at `GET /api/docs/`.
3. The system shall expose the raw OpenAPI schema at `GET /api/schema/`.
4. `drf-spectacular` shall be added as a project dependency in `pyproject.toml`.
5. `drf-spectacular` shall be added to `INSTALLED_APPS` and configured in `REST_FRAMEWORK` settings.
6. The OpenAPI metadata shall include title ("PeeBot API"), version, and a brief description.

## 4. Non-Functional Requirements

### 4.1 Performance (NFR-T006-001)

1. `/healthz` shall respond in < 10ms (no external calls).
2. `/readyz` shall respond in < 500ms under normal conditions (DB + Redis ping).
3. API list endpoints shall use database-level pagination to avoid loading entire tables into memory.

### 4.2 Security (NFR-T006-002)

1. Health check endpoints shall not expose sensitive information (no credentials, connection strings, or internal IPs).
2. The injection endpoint shall not be accessible in production without explicit opt-in (see FR-T006-004 §4).
3. API endpoints shall default to `AllowAny` permission for read-only endpoints (no user auth system exists per OOS-003).

### 4.3 Observability (NFR-T006-003)

1. The `/readyz` endpoint failures shall be captured by Sentry as breadcrumbs (not as errors — transient DB/Redis blips during deploys are expected). Implementation note: this requires explicitly calling `sentry_sdk.add_breadcrumb()` in the failure path and suppressing the 503 from Sentry's default Django error reporting (e.g., via `SENTRY_IGNORE_ERRORS` or custom `before_send` filtering for the health check path).
2. API request/response logging shall use the existing `structlog` pipeline configured for the project.

### 4.4 Testing (NFR-T006-004)

1. Health check endpoints shall have unit tests (mock DB/Redis for `/readyz` failure paths).
2. API list endpoints shall have integration tests verifying pagination, serialization, and empty-state responses.
3. The injection endpoint shall have tests covering: success path, validation failure, and `DEBUG=False` rejection.
4. After all T006 changes, `just test` shall pass with 0 errors and 0 collection/asyncio warnings.

### 4.5 Code Hygiene (NFR-T006-005)

1. All new code shall pass `ruff check` and `ruff format` without modifications.
2. All new code shall pass `uv run mypy apps/` with zero new errors.
3. New serializers and views shall follow the project's existing code style (see `docs/code_styleguides/python.md`).

## 5. Constraints

1. No new Django apps shall be created — health checks go in `apps/core`, API serializers go in their respective domain apps (C-001).
2. No authentication system shall be added — the API is read-only public per OOS-003. Only the injection endpoint has access control (C-002).
3. `drf-spectacular` is the only acceptable OpenAPI generator (not `drf-yasg` or manual schema) (C-003).
4. The existing Pydantic validation pipeline (`validator.py` + `enricher.py`) shall be reused for injection — no parallel validation logic (C-004).
5. All changes shall maintain backward compatibility with the existing 135-test suite (C-005).

## 6. Assumptions

1. `djangorestframework` is already installed and in `INSTALLED_APPS` — no dependency changes needed for the base API (A-001).
2. Redis is accessible from the Django process. The `/readyz` health check shall derive its Redis connection from the `CELERY_BROKER_URL` Django setting (which points to a Redis URL). No separate `REDIS_URL` setting exists in the current codebase (A-002).
3. The production Docker stack is already deployed and running on Coolify (A-003).
4. Python is available in the production Docker image for healthcheck commands. `curl` and `wget` are **not** installed in the runtime stage of the production Dockerfile (only `libpq5` is present) (A-004).

## 7. Acceptance Criteria

| ID | Criterion |
|:---|:---|
| AC-001 | `curl /healthz` returns `200 {"status": "ok"}` on a running instance |
| AC-002 | `curl /readyz` returns `200 {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}` when dependencies are up |
| AC-003 | `curl /readyz` returns `503` with failing check details when DB or Redis is down |
| AC-004 | `just test` produces 0 `PytestCollectionWarning` and 0 asyncio-related `PytestWarning` |
| AC-005 | `GET /api/v1/channels/` returns paginated JSON list of `TelemetryChannel` records |
| AC-006 | `GET /api/v1/events/` returns paginated JSON list of `DetectedEvent` records |
| AC-007 | `POST /api/v1/telemetry/inject/` with valid data creates a `TelemetryReading` and returns 201 |
| AC-008 | `POST /api/v1/telemetry/inject/` with invalid data returns 400 with validation errors |
| AC-009 | `POST /api/v1/telemetry/inject/` returns 403 when `DEBUG=False` (unless API key auth is implemented) |
| AC-010 | `GET /api/docs/` renders interactive Swagger UI |
| AC-011 | `GET /api/schema/` returns a valid OpenAPI 3.0 JSON/YAML schema |
| AC-012 | Prod compose `web` service has a working `healthcheck` directive |
| AC-013 | All 135+ existing tests continue to pass after changes |

## 8. Traceability

| Requirement | Satisfies |
|:---|:---|
| FR-T006-001 | Architecture §9.2 (Monitoring), Roadmap T006-1 |
| FR-T006-002 | Roadmap T006-2 (Code hygiene) |
| FR-T006-003 | System Overview §Communication §REST APIs, Roadmap T006-3 |
| FR-T006-004 | FR-ING-006 (Manual injection), Roadmap T006-4 |
| FR-T006-005 | Product Guidelines §Documentation, Roadmap T006-5 |
