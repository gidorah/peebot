# Tasks: T006 — Production Hardening

> Each task is an atomic, dependency-ordered change.
> Format: `_Req: <ID>_` traces back to `requirements.md`.

---

## Phase 1 — Fix Pytest Warnings

- [ ] **T006-01** Rename 8 `TestProcessor*` stub classes to `StubProcessor*`
  - *File*: `apps/event_processors/tests/test_base_processor.py`
  - Rename `TestProcessorLoadStateCreatesNew` → `StubProcessorLoadStateCreatesNew` (and the other 7 classes on lines 77–119). Update every instantiation reference in the test methods that use these classes.
  - *Req: FR-T006-002 §1, NFR-T006-004 §4*

- [ ] **T006-02** Move class-level `@pytest.mark.asyncio` to individual async methods
  - *File*: `apps/event_processors/tests/test_base_processor.py`
  - Remove the class-level `@pytest.mark.asyncio` from `TestBaseProcessorAbstractMethods` (L319). Add `@pytest.mark.asyncio` to the two async methods individually: `test_analyze_returns_detection_result` (L323) and `test_analyze_returns_none_when_no_event` (L336). The two sync methods (`test_get_confidence_returns_decimal`, `test_get_confidence_zero_for_empty`) must NOT carry the mark.
  - *Req: FR-T006-002 §2, NFR-T006-004 §4*

- [ ] **T006-03** Verify `just test` produces 0 collection/asyncio warnings
  - Run `just test`. Confirm **135 passed, 0 `PytestCollectionWarning`, 0 asyncio `PytestWarning`**. (2 structlog `UserWarning` and 1 teardown `PytestWarning` are pre-existing and out of T006 scope.)
  - *Req: FR-T006-002 §3, AC-004*

---

## Phase 2 — Health Check Endpoints

- [ ] **T006-04** Create `/healthz` liveness view
  - *File*: `apps/core/health.py` *(new)*
  - Plain Django function view. Returns `JsonResponse({"status": "ok"}, status=200)`. No auth, no DB calls.
  - *Req: FR-T006-001 §1, FR-T006-001 §3, NFR-T006-001 §1, NFR-T006-002 §1*

- [ ] **T006-05** Create `/readyz` readiness view
  - *File*: `apps/core/health.py`
  - Runs `SELECT 1` via `connection.cursor()` (DB check) and `redis.from_url(settings.CELERY_BROKER_URL).ping()` (Redis check). Returns 200 with `{"status": "ready", "checks": {"database": "ok", "redis": "ok"}}` when healthy; 503 with per-check error details otherwise. Log failures as Sentry breadcrumbs (`sentry_sdk.add_breadcrumb()`), not as errors. Additionally, suppress the 503 from Sentry's default Django error reporting (e.g., add a `before_send` filter or `SENTRY_IGNORE_ERRORS` rule for the `/healthz` and `/readyz` paths) so that rolling-deploy 503s do not create Sentry issues.
  - *Req: FR-T006-001 §2, FR-T006-001 §3, NFR-T006-001 §2, NFR-T006-002 §1, NFR-T006-003 §1*

- [ ] **T006-06** Wire `/healthz` and `/readyz` into root URL conf
  - *File*: `config/urls.py`
  - Import `healthz`, `readyz` from `apps.core.health`. Add `path("healthz", ...)` and `path("readyz", ...)` **before** `admin/` (not under `/api/`).
  - *Req: FR-T006-001 §4*

- [ ] **T006-07** Write health check unit tests
  - *File*: `apps/core/tests/test_health.py` *(new; create `apps/core/tests/__init__.py` if needed)*
  - Tests: `test_healthz_returns_200`, `test_readyz_returns_200_when_healthy` (mock DB + Redis OK), `test_readyz_returns_503_when_db_down`, `test_readyz_returns_503_when_redis_down`, `test_readyz_reports_both_failures`.
  - *Req: NFR-T006-004 §1, AC-001, AC-002, AC-003*

- [ ] **T006-08** Add `healthcheck` directive to prod `web` service
  - *File*: `docker/prod/docker-compose.yml`
  - Add under the `web:` service block: `healthcheck: test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]` with `interval: 30s`, `timeout: 10s`, `retries: 3`, `start_period: 15s`. Uses Python stdlib — no `curl`/`wget` in the prod image.
  - *Req: FR-T006-001 §5, AC-012*

---

## Phase 3 — REST API Skeleton

- [ ] **T006-09** Add `REST_FRAMEWORK` config dict to Django settings
  - *File*: `config/settings/base.py`
  - Add after `INSTALLED_APPS`: `REST_FRAMEWORK = {"DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination", "PAGE_SIZE": 50, "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"]}`.
  - *Req: FR-T006-003 §6, NFR-T006-002 §3*

- [ ] **T006-10** Create `TelemetryChannelSerializer`
  - *File*: `apps/telemetry_storage/serializers.py` *(new)*
  - `ModelSerializer` for `TelemetryChannel`. Inherit from `apps.core.serializers.BaseTelemetrySerializer` (existing base in `apps/core/serializers.py`). Fields: `id`, `public_pui`, `description`, `ops_nom`, `eng_nom`, `unit`.
  - *Req: FR-T006-003 §4, FR-T006-003 §8*

- [ ] **T006-11** Create `DetectedEventSerializer`
  - *File*: `apps/event_processors/serializers.py` *(new)*
  - `ModelSerializer` for `DetectedEvent`. Inherit from `apps.core.serializers.BaseTelemetrySerializer` (existing base in `apps/core/serializers.py`). Fields: `id`, `event_type`, `channel_id`, `detected_at`, `confidence`, `metadata`, `created_at`.
  - *Req: FR-T006-003 §5, FR-T006-003 §8*

- [ ] **T006-12** Create `TelemetryChannelViewSet` (read-only)
  - *File*: `apps/telemetry_storage/views.py`
  - `ReadOnlyModelViewSet` with `queryset = TelemetryChannel.objects.all()` and `serializer_class = TelemetryChannelSerializer`.
  - *Req: FR-T006-003 §4, FR-T006-003 §7, NFR-T006-001 §3*

- [ ] **T006-13** Create `DetectedEventViewSet` (read-only)
  - *File*: `apps/event_processors/views.py`
  - `ReadOnlyModelViewSet` with `queryset = DetectedEvent.objects.order_by("-detected_at")` and `serializer_class = DetectedEventSerializer`.
  - *Req: FR-T006-003 §5, FR-T006-003 §7, NFR-T006-001 §3*

- [ ] **T006-14** Create `config/api_urls.py` with DRF router
  - *File*: `config/api_urls.py` *(new)*
  - Instantiate `DefaultRouter`, register `channels` → `TelemetryChannelViewSet`, `events` → `DetectedEventViewSet`. Export `urlpatterns = router.urls`.
  - *Req: FR-T006-003 §1, FR-T006-003 §2*

- [ ] **T006-15** Wire `api/v1/` into root URL conf
  - *File*: `config/urls.py`
  - Add `path("api/v1/", include("config.api_urls"))`.
  - *Req: FR-T006-003 §3*

- [ ] **T006-16** Write REST API integration tests
  - *File*: `tests/test_api.py` *(new)*
  - Tests (DRF `APIClient`): `test_channels_list_200`, `test_channels_list_empty`, `test_events_list_200`, `test_events_ordered_by_detected_at_desc`, `test_channels_pagination` (seed 51+ records, verify `count`/`next`/`results`).
  - *Req: NFR-T006-004 §2, AC-005, AC-006*

---

## Phase 4 — Manual Injection Endpoint

- [ ] **T006-17** Create `ManualInjectionPayload` Pydantic model
  - *File*: `apps/telemetry_ingestion/services/injection.py` *(new)*
  - Fields: `pui: str`, `timestamp: datetime` (ISO 8601), `value: Decimal`, plus optional `calibrated_data`, `status_class`, `status_indicator`, `status_color`. Separate from the Lightstreamer `LightstreamerReading` model — no SOY timestamp conversion.
  - **Note**: FR-T006-004 §3 takes precedence over the literal wording of C-004 ("no parallel validation logic"). A dedicated injection Pydantic model is required because the enricher's only function (SOY → UTC) is irrelevant for ISO 8601 input. The validator pipeline is not duplicated — only a new input schema is added.
  - *Req: FR-T006-004 §2, C-004*

- [ ] **T006-18** Create `IsDebugMode` DRF permission class
  - *File*: `apps/core/permissions.py` *(new)*
  - `BasePermission` subclass. `has_permission` returns `settings.DEBUG`. Custom `message` for the 403 response.
  - *Req: FR-T006-004 §4, NFR-T006-002 §2*

- [ ] **T006-19** Create `TelemetryReadingSerializer` for injection response
  - *File*: `apps/telemetry_storage/serializers.py`
  - `ModelSerializer` for `TelemetryReading`. Fields: `id`, `channel`, `timestamp`, `value`, `calibrated_data`, `status_class`, `status_indicator`, `status_color`, `created_at`. Used to serialize the 201 response body.
  - *Req: FR-T006-004 §5*

- [ ] **T006-20** Implement `InjectTelemetryView` API view
  - *File*: `apps/telemetry_ingestion/views.py`
  - DRF `APIView` with `permission_classes = [IsDebugMode]`. `post()`: validate body with `ManualInjectionPayload`, resolve PUI via `TelemetryChannel.objects.get(public_pui=pui)` (404 if not found), build `ReadingData`, call `DjangoTelemetryRepository().create_reading()`, return 201 with serialized reading. Return 400 on Pydantic `ValidationError`.
  - *Req: FR-T006-004 §1, FR-T006-004 §3, FR-T006-004 §5, FR-T006-004 §6*

- [ ] **T006-21** Register injection URL in API router
  - *File*: `config/api_urls.py`
  - Append `path("telemetry/inject/", InjectTelemetryView.as_view(), name="telemetry-inject")` to `urlpatterns`.
  - *Req: FR-T006-004 §1*

- [ ] **T006-22** Write injection endpoint tests
  - *File*: `apps/telemetry_ingestion/tests/test_injection.py` *(new)*
  - Tests: `test_inject_success_201` (valid payload → `TelemetryReading` created), `test_inject_unknown_pui_404`, `test_inject_missing_field_400`, `test_inject_blocked_debug_false_403` (`@override_settings(DEBUG=False)`), `test_inject_allowed_debug_true_201`.
  - *Req: NFR-T006-004 §3, AC-007, AC-008, AC-009*

---

## Phase 5 — OpenAPI Documentation

- [ ] **T006-23** Add `drf-spectacular` to project dependencies
  - *File*: `pyproject.toml`
  - Add `"drf-spectacular>=0.28.0"` to `dependencies`. Run `uv lock && uv sync`.
  - *Req: FR-T006-005 §4, C-003*

- [ ] **T006-24** Register `drf-spectacular` in Django settings
  - *File*: `config/settings/base.py`
  - Add `"drf_spectacular"` to `INSTALLED_APPS`. **Append** `"DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema"` to the existing `REST_FRAMEWORK` dict created in T006-09 — do not replace it. Add `SPECTACULAR_SETTINGS` dict with `TITLE`, `DESCRIPTION`, `VERSION`.
  - *Req: FR-T006-005 §5, FR-T006-005 §6*

- [ ] **T006-25** Wire `/api/schema/` and `/api/docs/` URLs
  - *File*: `config/urls.py`
  - Add `path("api/schema/", SpectacularAPIView.as_view(), name="schema")` and `path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui")`.
  - *Req: FR-T006-005 §1, FR-T006-005 §2, FR-T006-005 §3*

- [ ] **T006-26** Write OpenAPI smoke tests
  - *File*: `tests/test_api.py`
  - Append: `test_openapi_schema_returns_200` (`GET /api/schema/`), `test_swagger_ui_returns_200` (`GET /api/docs/`).
  - *Req: AC-010, AC-011*

---

## Phase 6 — Final Validation

- [ ] **T006-27** Run full test suite — 0 errors, 0 target warnings
  - Run `just test`. All pre-existing 135 + new tests pass. No `PytestCollectionWarning`, no asyncio `PytestWarning`. Verify API request/response logging reaches structlog (satisfies NFR-T006-003 §2 implicitly via DRF's built-in logging; if not, add `django_structlog.middlewares.RequestMiddleware` to `MIDDLEWARE`).
  - *Req: NFR-T006-004 §4, NFR-T006-003 §2, AC-004, AC-013, C-005*

- [ ] **T006-28** Run linting and type-checking
  - `uv run ruff check apps/ config/ tests/` → 0 errors. `uv run ruff format --check apps/ config/ tests/` → 0 reformatted. `uv run mypy apps/` → 0 new errors.
  - *Req: NFR-T006-005 §1, NFR-T006-005 §2*

- [ ] **T006-29** Validate prod Docker Compose config
  - `docker compose -f docker/prod/docker-compose.yml config > /dev/null` → exit 0.
  - *Req: AC-012*
