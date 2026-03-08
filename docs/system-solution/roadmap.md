# PeeBot Roadmap — Gap Analysis & Implementation Plan

**Generated**: 2026-03-01
**Baseline**: All docs in `/docs/incoming/`, `/docs/system-solution/`, and `/conductor/`
**Methodology**: Cross-referenced every FR, NFR, BO, and architectural spec against the live codebase.

---

## Executive Summary

PeeBot's core pipeline is **fully operational**: ingestion → storage → event detection → Bluesky posting. Production deployment (T005), Sentry observability (error tracking, logs, Celery Crons, custom metrics), and the `SOCIAL_DRY_RUN` mode are all shipped. **135 tests pass.**

The remaining work falls into three categories:

| Category | Scope | Effort |
|:---|:---|:---|
| **Production Hardening** | Health checks, API foundations, code hygiene | Small (1-2 days) |
| **Dashboard (BO-4)** | Full web UI — channels, charts, live updates | Large (2-3 weeks) |
| **Operational Maturity** | Load testing, continuous aggregates (Sentry-only, no Prometheus) | Small-Medium (3-5 days) |

---

## 1. Requirements Satisfaction Matrix

### 1.1 Business Objectives

| ID | Objective | Status |
|:---|:---|:---|
| **BO-1** | Ingest real-time telemetry with zero duplication | ✅ Complete (T001, T002, T004) |
| **BO-2** | Detect UPA events via sliding-window analysis | ✅ Complete (T003) |
| **BO-3** | Automated humorous Bluesky posts | ✅ Complete (T003 — JokeGenerator + BlueskyClient) |
| **BO-4** | Low-latency web dashboard | ❌ **Not Started** |
| **BO-5** | Operationally simple modular monolith | ✅ Complete (single compose stack, Coolify) |

### 1.2 Functional Requirements

| ID | Requirement | Status | Notes |
|:---|:---|:---|:---|
| FR-CORE-001 | UUIDv7 + timestamp base models | ✅ | `core.models` |
| FR-CORE-002 | DRF serializers for Lightstreamer mapping | ✅ | Pydantic for hot path (ADR-004) |
| FR-CORE-003 | Timestamp normalization | ✅ | `enricher.py` |
| FR-ING-001 | Persistent async Lightstreamer connection | ✅ | `LightstreamerClient` + async bridge |
| FR-ING-002 | Reconnection with exponential backoff | ✅ | `run_lightstreamer.py` |
| FR-ING-003 | Schema validation (Pydantic) | ✅ | `validator.py` |
| FR-ING-004 | UUIDv7 enrichment + ingested_at | ✅ | Model defaults (ADR-007) |
| FR-ING-005 | Batch abulk_create persistence | ✅ | With `ignore_conflicts=True` (ADR-011) |
| FR-ING-006 | REST API endpoint for manual injection | ❌ | DRF installed, no view defined |
| FR-STO-001 | TimescaleDB hypertable (1-day chunks) | ✅ | Migration + init-timescale.sql |
| FR-STO-002 | Auto compression (7 days) | ✅ | Retention policy active |
| FR-STO-003 | Auto retention (30 days) | ✅ | Retention policy active |
| FR-STO-004 | Composite unique (channel, timestamp) | ✅ | ADR-011 |
| FR-STO-005 | ~400 channel metadata | ✅ | `seed_channels` command + PUIList.xml |
| FR-PROC-001 | Celery Beat polling | ✅ | 30s static schedule (ADR-009) |
| FR-PROC-002 | PeeBot queries NODE3000005 every 30s | ✅ | `PeeBotProcessor` |
| FR-PROC-003 | Two-phase detection algorithm | ✅ | Burst detection + stability check |
| FR-PROC-004 | LLM-generated humor (DeepSeek V3) | ✅ | `JokeGenerator` via OpenRouter |
| FR-PROC-005 | Bluesky posting with 30-min cooldown | ✅ | `BlueskyClient` + SocialPost tracking |
| FR-DASH-001 | Live status web interface | ❌ | **Not Started** |
| FR-DASH-002 | Searchable channel browser (~400) | ❌ | **Not Started** |
| FR-DASH-003 | High-priority channels via WebSocket | ❌ | **Not Started** (no Channels dep) |
| FR-DASH-004 | HTMX polling (2-3s) for standard updates | ❌ | **Not Started** (no HTMX dep) |
| FR-DASH-005 | Interactive time-series charts | ❌ | **Not Started** |

### 1.3 Non-Functional Requirements

| ID | Requirement | Status | Notes |
|:---|:---|:---|:---|
| NFR-PERF-001 | 70 msg/s nominal, 10K burst | ✅ | Async bridge + abulk_create |
| NFR-PERF-002 | Persistence latency P99 < 5s | ✅ | Smart buffering (2000 items / 500ms) |
| NFR-PERF-003 | Dashboard latency P99 < 1s | ❌ | No dashboard exists |
| NFR-PERF-004 | Analytics detection < 2 min | ✅ | 30s polling cycle |
| NFR-ARCH-001 | Modular monolith boundaries | ✅ | Strict module ownership enforced |
| NFR-ARCH-002 | TimescaleDB single source of truth | ✅ | No Kafka, no duplicate stores |
| NFR-ARCH-003 | PgBouncer connection pooling | ✅ | Session mode, dev + prod |
| NFR-REL-001 | Graceful upstream interruption handling | ✅ | Backoff + queue backpressure |
| NFR-REL-002 | Processor state for resumption | ✅ | `ProcessorState` model |

### 1.4 Architecture Spec — Missing Pieces

| Component | Specified In | Status |
|:---|:---|:---|
| Health check endpoints | Architecture §9.2 (Monitoring) | ✅ Implemented (`/healthz`, `/readyz`) |
| REST API (`/api/v1/channels/`, `/api/v1/events/`) | System Overview §Communication | ✅ Implemented |
| ~~Prometheus / Grafana~~ | ~~Architecture §9.2, System Overview §Monitoring~~ | ⊘ **CANCELLED** (Decision #3: Sentry-only) |
| Sentry error tracking | Architecture §9.2 | ✅ Implemented (ADR-015) |
| Django Channels + Daphne (ASGI) | Architecture §3, §8.5 | ❌ Not implemented |
| Continuous Aggregates | System Overview §TimescaleDB Optimizations | ❌ Not implemented |
| OpenAPI/Swagger docs | Product Guidelines §Documentation | ✅ Implemented (`/api/schema/`, `/api/docs/`) |

---

## 2. Code Hygiene Issues

| Issue | Location | Severity |
|:---|:---|:---|
| 8 `PytestCollectionWarning` — test classes with `__init__` | `test_base_processor.py` L77-119 | ✅ Resolved in T006 |
| 2 sync tests marked `@pytest.mark.asyncio` | `test_base_processor.py` L344, L354 | ✅ Resolved in T006 |
| 1 teardown `OperationalError` (DB still accessed) | `test_validator.py` | Low (intermittent) |
| `django-celery-beat` installed but unused | `pyproject.toml` | Low (dead dependency, keep per ADR-009) |
| `djangorestframework` in INSTALLED_APPS but no views | `config/settings/base.py` | ✅ Resolved in T006 |

---

## 3. Proposed Roadmap

### Phase 6: Production Hardening (T006)

**Priority**: Critical — needed for operational reliability of the already-deployed system.
**Effort**: ~1-2 days
**Dependencies**: None

| Task | Description | Satisfies |
|:---|:---|:---|
| T006-1 | **Health check endpoints** — Add `/healthz` (liveness: returns 200) and `/readyz` (readiness: DB + Redis ping). Wire into prod compose `healthcheck` for `web` service. | Architecture §9.2 |
| T006-2 | **Fix pytest warnings** — Rename 8 test classes with `__init__` constructors to avoid `PytestCollectionWarning`. Remove 2 spurious `@pytest.mark.asyncio` marks from sync tests. | Code hygiene |
| T006-3 | **REST API skeleton** — Create `config/api_urls.py` with DRF router. Add `api/v1/` URL namespace in `config/urls.py`. Implement `GET /api/v1/channels/` (list) and `GET /api/v1/events/` (list, paginated) read-only endpoints. | FR-ING-006 foundational setup |
| T006-4 | **Manual injection endpoint** — `POST /api/v1/telemetry/inject/` using existing Pydantic validator + enricher + repository. Restrict to `DEBUG=True` or API key auth. | FR-ING-006 |
| T006-5 | **OpenAPI docs** — Enable DRF's `SpectacularSwaggerView` at `/api/docs/` for self-documenting API. | Product Guidelines §Documentation |

### Phase 7: Dashboard — Foundation (T007)

**Priority**: High — BO-4 is the last unstatisfied business objective.
**Effort**: ~1 week
**Dependencies**: T006-3 (API skeleton)

| Task | Description | Satisfies |
|:---|:---|:---|
| T007-1 | **Add frontend dependencies** — Install `django-channels`, `daphne`, add HTMX (CDN or vendored), **Tailwind CSS** (Decision #1). Update `INSTALLED_APPS` and ASGI config. | Architecture §3, §8.5 |
| T007-2 | **Base templates** — Create base layout with navigation (channel browser link, event timeline link, live status). Include HTMX script and Chart.js CDN. | FR-DASH-001 |
| T007-3 | **Dashboard homepage** — Live status view showing system health (ingestion active, last reading time, total channels, recent events count). HTMX polling every 3s for status fragment. | FR-DASH-001, FR-DASH-004 |
| T007-4 | **Channel browser** — Paginated, searchable list of all ~400 `TelemetryChannel` records with latest reading value. HTMX-powered search and pagination. | FR-DASH-002 |
| T007-5 | **Channel detail page** — Show channel metadata + last 100 readings in a table. Stub area for Chart.js visualization. | FR-DASH-002, FR-DASH-005 (partial) |
| T007-6 | **Event timeline** — List of `DetectedEvent` records with drill-down to detection metadata and linked `SocialPost`. | FR-DASH-001 |

### Phase 8: Dashboard — Real-Time & Charts (T008)

**Priority**: High — completes BO-4 and satisfies remaining FR-DASH requirements.
**Effort**: ~1 week
**Dependencies**: T007

| Task | Description | Satisfies |
|:---|:---|:---|
| T008-1 | **WebSocket consumer** — Create `TelemetryConsumer` using Django Channels for real-time updates on "high-priority" channels. Redis as channel layer. | FR-DASH-003 |
| T008-2 | **Priority channel subscription** — Allow users to mark channels as high-priority. WebSocket pushes live readings for subscribed channels. | FR-DASH-003 |
| T008-3 | **Event notification consumer** — Push detected events via WebSocket (toast notification on dashboard). | FR-DASH-003 |
| T008-4 | **Chart.js time-series** — Interactive line charts on channel detail pages. X-axis: time, Y-axis: value. Zoom/pan support. Data from REST API endpoint with configurable time range. | FR-DASH-005, NFR-PERF-003 |
| T008-5 | **Redis caching layer** — Cache HTMX fragments in Redis (5s TTL) for dashboard overview and channel list. | Architecture §8.5, NFR-PERF-003 |
| T008-6 | **Dashboard tests** — Unit tests for views, WebSocket consumer tests using `channels.testing`, HTMX response tests. | Workflow §2 |

### Phase 9: Operational Maturity (T009)

**Priority**: Medium — improves observability beyond Sentry; validates performance claims.
**Effort**: ~3-5 days
**Dependencies**: T007 (dashboard exists for metrics to reference)

| Task | Description | Satisfies |
|:---|:---|:---|
| T009-1 | **Continuous aggregates** — Create TimescaleDB continuous aggregates for hourly averages and daily min/max per channel. Used by dashboard charts for zoomed-out views. | System Overview §TimescaleDB Optimizations |
| ~~T009-2~~ | ~~Prometheus metrics endpoint~~ — **CANCELLED** (Decision #3: Sentry-only metrics). | ~~Architecture §9.2~~ |
| ~~T009-3~~ | ~~Grafana dashboard~~ — **CANCELLED** (Decision #3: Sentry-only metrics). | ~~Architecture §9.2~~ |
| T009-4 | **Load testing suite** — k6 or locust script simulating 10K msg/sec ingestion burst. Validate NFR-PERF-001 and NFR-PERF-002 under load. Document results. | System Overview §Phase 6 |
| T009-5 | **Performance tuning** — Based on load test results: tune PgBouncer pools, Gunicorn workers, Celery concurrency, abulk_create batch size. | System Overview §Performance |

### Phase 10: Polish & Documentation (T010)

**Priority**: Low — quality-of-life improvements after all features are complete.
**Effort**: ~1-2 days
**Dependencies**: T008, T009

| Task | Description | Satisfies |
|:---|:---|:---|
| T010-1 | **README overhaul** — Update README.md with current architecture diagram, setup instructions, feature list, screenshots of dashboard. | Product Guidelines §Documentation |
| T010-2 | **ADR updates** — Record decisions for dashboard tech stack (Channels, HTMX, Chart.js), Prometheus addition, continuous aggregates. | ADR protocol |
| T010-3 | **Update main-tasks.md** — Mark T006-T010 entries in the project roadmap with completion dates. | SDD Protocol §Phase 4 |
| T010-4 | **Dependency audit** — Remove `django-celery-beat` if still unused, or document its retention. Verify all deps are used. | Code hygiene |
| T010-5 | **CI pipeline** — GitHub Actions workflow: lint (ruff), typecheck (mypy), test (pytest with TimescaleDB service container). Coolify handles deployment separately via git-push trigger (Decision #4). | Workflow §3 |

---

## 4. Dependency Graph

```
T006 (Hardening)          ← No dependencies, start immediately
  │
  ├── T006-1 (Health checks)
  ├── T006-2 (Fix warnings)
  ├── T006-3 (API skeleton)  ──┐
  ├── T006-4 (Injection EP)    │
  └── T006-5 (OpenAPI docs)    │
                                │
T007 (Dashboard Foundation) ←───┘  Depends on T006-3
  │
  ├── T007-1 (Frontend deps)
  ├── T007-2 (Base templates)
  ├── T007-3 (Homepage)
  ├── T007-4 (Channel browser)
  ├── T007-5 (Channel detail)
  └── T007-6 (Event timeline)
          │
T008 (Dashboard Real-Time) ←── Depends on T007
  │
  ├── T008-1 (WebSocket consumer)
  ├── T008-2 (Priority channels)
  ├── T008-3 (Event notifications)
  ├── T008-4 (Chart.js)
  ├── T008-5 (Redis caching)
  └── T008-6 (Dashboard tests)

T009 (Operational Maturity) ←── Can start after T007 (parallel with T008)
  │
  ├── T009-1 (Continuous aggregates)
  ├── T009-4 (Load testing)
  └── T009-5 (Performance tuning)

T010 (Polish) ←── After T008 + T009
```

---

## 5. Estimated Timeline

| Phase | Calendar Estimate | Cumulative |
|:---|:---|:---|
| T006 — Production Hardening | 1-2 days | Week 1 |
| T007 — Dashboard Foundation | 5-7 days | Week 2 |
| T008 — Dashboard Real-Time | 5-7 days | Week 3 |
| T009 — Operational Maturity | 2-3 days | Week 3-4 (parallel with T008) |
| T010 — Polish & Documentation | 1-2 days | Week 4 |

**Total remaining effort**: ~3 weeks to full specification compliance.

---

## 6. Risk Register

| Risk | Impact | Mitigation |
|:---|:---|:---|
| Django Channels + Daphne adds ASGI complexity to prod compose | Medium | Start with HTMX-only dashboard (T007), add WebSocket layer (T008) separately |
| TimescaleDB continuous aggregates require careful migration | Low | Test in dev first, use `IF NOT EXISTS` guards |
| Load testing may reveal bottlenecks requiring architecture changes | Medium | Run early (T009-4), budget time for T009-5 tuning |
| Chart.js bundle size could slow dashboard load | Low | Use CDN, lazy-load chart library only on detail pages |
| WebSocket scaling on single VPS (Daphne memory) | Medium | Limit WebSocket connections, use HTMX polling as primary update mechanism |

---

## 7. Out of Scope (Confirmed)

Per SRS §7, the following remain explicitly excluded:
- OOS-001: Microservices architecture
- OOS-002: Data archival beyond 30 days
- OOS-003: User authentication for dashboard (read-only public)
- OOS-004: Two-way ISS control

---

## 8. Decision Log

| # | Decision | Choice | Date | Impact |
|:---|:---|:---|:---|:---|
| 1 | **CSS framework for dashboard** | **Tailwind CSS** — utility-first, smaller builds, no component lock-in | 2026-03-01 | T007-1 |
| 2 | **Chart library** | **TBD** — defer until T008-4 implementation begins | 2026-03-01 | T008-4 |
| 3 | **Metrics stack** | **Sentry-only** — no Prometheus/Grafana. Custom metrics via `sentry_sdk.metrics` (ADR-015) are sufficient. Eliminates T009-2 and T009-3. | 2026-03-01 | T009 scope reduced |
| 4 | **CI provider** | **GitHub Actions** — native to GitHub repo, Coolify handles deployment separately (git-push triggered) | 2026-03-01 | T010-5 |
