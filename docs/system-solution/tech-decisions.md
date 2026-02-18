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
