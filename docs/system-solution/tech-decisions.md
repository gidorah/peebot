# Architectural Decision Records (ADR)

## ADR-001: Modular Monolith Architecture
*   **Decision**: Django Modular Monolith.
*   **Status**: Accepted.
*   **Rationale**: Reduces operational complexity (single deployment unit) while enforcing strict boundaries (module ownership) to prevent spaghetti code. Avoids distributed system fallacies of microservices for a team of this size.

## ADR-002: Ingestion Strategy
*   **Decision**: Official `lightstreamer-client-lib` (Threaded) with Async Bridge.
*   **Status**: Accepted.
*   **Rationale**: The official library is stable and maintained. While blocking, running it in a dedicated management command with an in-memory buffer that flushes to Django's Async ORM provides sufficient throughput (70 msg/sec target) without the risk of maintaining a custom WebSocket protocol implementation.

## ADR-003: Database Engine
*   **Decision**: TimescaleDB (PostgreSQL Extension).
*   **Status**: Accepted.
*   **Rationale**: Telemetry data is inherently time-series. Hypertables provide O(1) partitioning performance and native compression (90% storage reduction), critical for the "Single Source of Truth" requirement.

## ADR-004: High-Performance Ingestion Validation
*   **Decision**: Pydantic and Direct Dict Manipulation (Bypassing DRF).
*   **Status**: Accepted.
*   **Rationale**: To handle 10k msg/sec bursts, the CPU overhead of instantiating Django REST Framework serializers is too high. We use Pydantic for the "hot path" ingestion pipeline to ensure the Consumer Loop does not become a bottleneck, reserving DRF for standard REST APIs.

## ADR-005: Channel Resolution Strategy
*   **Decision**: In-Process Memory Map (Dictionary).
*   **Status**: Accepted.
*   **Rationale**: To meet the ingestion throughput target, we require nanosecond-level resolution of PUI strings (e.g., "NODE3000005") to Database UUIDs.
    *   **Implementation**: A Python dictionary is pre-loaded from the DB at startup.
    *   **Trade-off**: Adding new channels requires a process restart (or a periodic refresh implementation). This "stale data" risk is acceptable because Channel definitions are static configuration data that change extremely rarely.
    *   **Alternative Rejected**: Redis cache was rejected for the hot path due to network I/O latency (~0.5ms per message) which would degrade performance during high-frequency bursts.

## ADR-006: Centralized Structured Logging
*   **Decision**: Structlog + Seq.
*   **Status**: Accepted.
*   **Rationale**:
    *   **Structure**: Moving from text-based logs (`grep`) to structured events allows filtering by `request_id`, `user_id`, or `channel` across distributed services (Web, Worker, Beat).
    *   **Tooling**: Seq provides a zero-config, powerful search UI for development that is far superior to docker-compose logs.
    *   **Implementation**: `Structlog` ensures consistent JSON context injection across the stack. A custom `SeqHandler` manages async dispatch to the Seq container.

## ADR-007: Hybrid Enrichment Strategy
*   **Decision**: Separation of Domain Normalization and System Metadata.
*   **Status**: Accepted.
*   **Rationale**:
    *   **Domain Data**: Complex logic like converting "Hours since start of year" to UTC Datetime and handling Year Rollover requires explicit business logic. This is delegated to `apps.telemetry_ingestion.services.enricher.py`.
    *   **System Metadata**: Standard fields like `id` (UUIDv7) and `created_at` (Ingestion Time) are handled efficiently by Django Model defaults (`UUID7Model`, `TimeStampedModel`) upon instantiation, reducing boilerplate in the ingestion loop.

## ADR-008: Ingestion Queue Safety Pattern
*   **Decision**: Robust Queue Handling with Backpressure & Loop Safety.
*   **Status**: Accepted.
*   **Rationale**:
    *   **Backpressure**: When the `asyncio.Queue` is full (`maxsize=50000`), the producer loop drops the oldest message (`get_nowait()`) to make room for new data. This prevents memory leaks and ensures we always ingest the freshest data during bursts.
    *   **Loop Safety**: The consumer loop tracks the exact number of items pulled from the queue and guarantees `task_done()` is called for that count in a `finally` block. This prevents the pipeline from hanging (deadlock on `queue.join()`) even if the DB flush operation fails or raises an exception.

## ADR-009: Celery Beat Scheduling Strategy
*   **Decision**: Static code-defined `beat_schedule` with Celery's default `PersistentScheduler`. Remove `DatabaseScheduler`.
*   **Status**: Accepted.
*   **Context**: The initial T003 implementation configured `DatabaseScheduler` (via `django_celery_beat`) in Django settings while simultaneously defining the schedule statically in `config/celery.py`. `DatabaseScheduler` seeds from the static dict on first run but then the DB takes precedence — subsequent code changes to intervals are silently ignored, creating a disconnect between version control and runtime behavior.
*   **Rationale**:
    *   **Single task, fixed interval**: PeeBot has one periodic task (`run_peebot_processor`) at a fixed 30-second interval. The operational overhead of DB-managed schedules is unjustified.
    *   **Version-controlled schedules**: Static `beat_schedule` ensures schedule changes are reviewed in PRs and deployed deterministically, eliminating "stale DB entry" drift.
    *   **Zero DB overhead**: No `PeriodicTask` table polling, no extra migration tables, no Django Admin schedule management to maintain.
    *   **Reversible**: `django_celery_beat` remains as a dependency and can be re-enabled if runtime schedule management becomes a real need (e.g., multiple processors with operator-adjustable intervals).
*   **Alternative Rejected**: `DatabaseScheduler` with a seeding management command (`update_or_create` pattern) was considered for future-proofing but rejected as premature complexity.

## ADR-010: Event Detection vs. Posting Cooldown Separation
*   **Decision**: Apply 30-minute cooldown to social media posting only, not to event detection. Fix cursor advancement to prevent duplicate detection.
*   **Status**: Accepted.
*   **Context**: Code review identified a cursor bug where `ProcessorState.last_processed_timestamp` was set to `detection.detected_at` (burst start time) after event detection. On the next run, readings from the middle of the already-detected burst would be re-queried, potentially causing duplicate event detection. Initial fix attempt added a 30-minute cooldown on event detection itself, but documentation research (FR-PROC-005, design.md flowchart) revealed the 30-minute cooldown was specified only for Bluesky posting, not detection.
*   **Rationale**:
    *   **Documented Intent**: FR-PROC-005 states "30-minute cooldown period between **posts**". The design.md flowchart shows `DetectedEvent.create()` happening **before** the cooldown check. Events are always persisted; cooldown only gates posting.
    *   **Multiple Events**: Real-world scenario may have multiple urination events within 30 minutes. Suppressing detection would lose valuable data. The system should detect all events but rate-limit social announcements.
    *   **Cursor Fix as Root Solution**: Setting `last_processed_timestamp = max(r.timestamp for r in readings)` (latest reading) instead of `detection.detected_at` (burst start) naturally prevents re-detection without needing a separate cooldown mechanism. The processor window advances past the entire burst.
    *   **Separation of Concerns**: Event detection (analytics accuracy) and social posting (rate-limiting, spam prevention) are distinct concerns with different requirements.
*   **Implementation**:
    *   `apps/event_processors/tasks.py` Step 7: Cursor updated to `max(r.timestamp for r in readings)` after both detection and no-detection paths.
    *   Bluesky posting cooldown remains via `BlueskyClient.check_cooldown()` querying `SocialPost` table.
    *   Test added: `test_run_peebot_processor_cursor_advances_past_burst` verifies cursor is at latest reading, not burst start.
*   **Alternative Rejected**: Event detection cooldown querying `DetectedEvent` table was implemented but reverted after documentation research revealed it contradicted the documented architecture.

## ADR-011: Duplicate Reading Prevention via Composite Unique Constraint
*   **Decision**: Enforce `(channel, timestamp)` composite uniqueness on `TelemetryReading` and use `ignore_conflicts=True` on all batch inserts.
*   **Status**: Accepted.
*   **Context**: The initial data model defined a `UniqueConstraint(fields=["id", "timestamp"])`, which is semantically a no-op since `id` (UUIDv7) is already globally unique per row. On service restart, Lightstreamer re-broadcasts the latest snapshot values for all subscribed channels. These arrive with identical `(channel, timestamp)` pairs as readings already persisted in the previous session — but the useless constraint cannot prevent them, resulting in duplicate rows and violating BO-1 ("zero data duplication"). A compounding defect in the ingestion path called `abulk_create(readings)` without `ignore_conflicts=True`, meaning any genuine constraint violation would raise an `IntegrityError` and silently abort the entire batch via the broad `except Exception` handler.
*   **Rationale**:
    *   **Logical Deduplication Key**: `(channel, timestamp)` is the true uniqueness predicate — at most one reading should exist per channel at any given instant.
    *   **Restart Safety**: With `ignore_conflicts=True`, duplicate `(channel, timestamp)` pairs on restart are silently skipped by PostgreSQL (`ON CONFLICT DO NOTHING`). First-write-wins semantics prevent data loss while keeping the database clean.
    *   **TimescaleDB Compatibility**: All unique indexes on a hypertable must include the partition key (`timestamp`). The constraint `(channel_id, timestamp)` satisfies this requirement without touching the composite primary key `(id, timestamp)` established for the hypertable.
    *   **Analytics Correctness**: Analytics modules query `TelemetryReading` ordered by `timestamp`. Duplicate timestamps for the same channel cause the sliding-window algorithm to produce unstable `net_delta` values. Enforcing uniqueness at the database layer eliminates this edge case without any changes to the algorithm.
*   **Implementation**:
    *   `apps/telemetry_storage/models.py`: Replace `UniqueConstraint(fields=["id", "timestamp"], name="unique_id_timestamp")` with `UniqueConstraint(fields=["channel", "timestamp"], name="unique_channel_timestamp")`.
    *   Migration `0004_fix_unique_constraint`: Drop `unique_id_timestamp`, add `unique_channel_timestamp`.
    *   `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`: Add `ignore_conflicts=True` to `abulk_create()` call.
*   **Alternative Rejected**: Application-layer deduplication (checking for existing readings before insert) was rejected. It adds latency, introduces race conditions under concurrent ingestion, and provides weaker guarantees than a database-enforced constraint.

## ADR-012: Baked Docker Images for Production
*   **Decision**: Use multi-stage Docker builds that bake all application code and dependencies into the image at build time. No volume mounts or runtime `uv sync`.
*   **Status**: Accepted.
*   **Context**: The dev environment mounts the repo as a volume (`../../:/workspace`) and runs `uv sync --frozen --dev` on every container start for rapid iteration. For production, this pattern creates startup latency (~30s for dependency resolution), exposes source code on the host filesystem, and makes deployments non-reproducible (runtime depends on host state and network availability for package downloads).
*   **Rationale**:
    *   **Reproducibility**: A built image is immutable and tagged. The same image runs identically in any environment (CI, staging, production). There is no risk of dependency resolution differences between builds.
    *   **Security**: Source code and `.env` files are not present on the host. The attack surface is limited to the runtime dependencies in the image. The non-root user (`python`, UID 1000) cannot modify application code.
    *   **Startup Time**: Containers boot in <2 seconds (vs. 30s+ with `uv sync`). This matters for restarts, scaling, and health check responsiveness.
    *   **Coolify Compatibility**: Coolify's Docker Compose deployment naturally builds images from Dockerfiles. Baked images align with Coolify's clone-build-deploy pipeline without requiring host-side setup.
    *   **Image Reuse**: All 4 application services (web, worker, beat, ingestion) share the same image, differing only in `command:`. This reduces build time and storage.
*   **Alternative Rejected**: Keeping volume mounts with `uv sync` at runtime was considered for "parity with dev" but rejected due to the security, reliability, and performance drawbacks in production.

## ADR-013: Stdout-only Logging in Production
*   **Decision**: All production logs go to stdout/stderr. No Seq, no file handlers. Structlog is used as the application logging API with a plain stdout renderer.
*   **Status**: Amended (see below).
*   **Context**: The dev environment uses structlog with Rich console formatting and Seq (CLEF over HTTP) for centralized structured log search. The initial production settings used file-based logging to `logs/django.log`, which is problematic in containers (files are lost on restart, require volume mounts, and aren't accessible via Coolify's log viewer).
*   **Rationale**:
    *   **Docker-native**: Docker captures stdout/stderr from containers and makes logs available via `docker logs`, which Coolify's UI surfaces directly. No additional log infrastructure is needed.
    *   **Zero overhead**: No Seq container (saves ~500MB RAM), no HTTP log shipping (saves network/CPU), no SeqHandler processing pipeline.
    *   **Resource constraints**: The 4 vCPU / 8 GB VPS is shared with other services. Seq would consume significant memory for marginal benefit on a single-app deployment.
    *   **Simplicity**: Plain stdout via `logging.StreamHandler` is well-understood, debuggable, and has zero dependencies beyond the standard library.
    *   **Future upgrade path**: If structured log search becomes necessary, Coolify supports log drains to external services (Loki, CloudWatch). This can be added without changing application code.
*   **Amendment**: The original ADR stated "No Seq, no structlog, no file handlers." This was revised to keep `structlog` as the application logging API in production. The codebase uses `structlog.get_logger()` and `logger.bind()` throughout `apps/event_processors/` for structured context propagation (attaching `processor_name`, `event_id`, `channel_id` to every log line in a run). Replacing this with stdlib `logging` would require `LoggerAdapter` boilerplate or manual `extra={}` dicts on every call, with no meaningful benefit. The `structlog` library is ~70KB with zero additional dependencies. The production configuration uses `structlog.stdlib.LoggerFactory()` + `ConsoleRenderer(colors=False)` to render key=value output to stdout — no Seq, no HTTP shipping, no Rich. The original intent (eliminating logging infrastructure overhead) is fully preserved.
*   **Alternative Rejected**: Deploying Seq in production was considered but rejected due to memory cost (~500MB-1GB) on a constrained VPS.

## ADR-014: Coolify Docker Compose Deployment
*   **Decision**: Deploy PeeBot as a single Docker Compose stack managed by Coolify, with environment variables injected via the Coolify UI.
*   **Status**: Accepted.
*   **Context**: PeeBot runs on a single Hetzner VPS (4 vCPU, 8 GB RAM) managed by Coolify. Coolify supports multiple deployment modes: Dockerfile, Docker Compose, Nixpacks, and static builds. The project already has a `docker/prod/docker-compose.yml` with all required services.
*   **Rationale**:
    *   **All-in-one management**: Docker Compose deploys all 7 services (TimescaleDB, PgBouncer, Redis, web, worker, beat, ingestion) as a single stack with defined dependencies, health checks, and networking. Coolify monitors the entire stack as one unit.
    *   **Environment variables via UI**: Coolify injects env vars into all containers, eliminating `env_file` directives and the need to manage `.env` files on the server. Secrets are stored in Coolify's encrypted storage.
    *   **TLS termination**: Coolify's built-in Traefik proxy handles TLS certificates (Let's Encrypt) and domain routing. Django does not need to manage certificates or SSL redirects.
    *   **Git-driven deploys**: Coolify watches the connected Git repo and triggers builds on push (or manual trigger). The compose file path (`docker/prod/docker-compose.yml`) is configured in Coolify's project settings.
    *   **Compose file location**: The compose file stays at `docker/prod/docker-compose.yml` rather than the repo root, maintaining the existing directory structure and separation of dev/prod configurations.
*   **Alternative Rejected**: Deploying each service as a separate Coolify resource was considered for independent scaling, but rejected because it adds operational complexity (7 separate Coolify resources, manual dependency management) without benefit for a single-VPS deployment with fixed resource limits.
