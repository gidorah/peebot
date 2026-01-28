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
*   **Rationale**: To meet the ingestion throughput target, we require nanosecond-level resolution of PUI strings (e.g., "NODE3000004") to Database UUIDs. 
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
