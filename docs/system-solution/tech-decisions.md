# Technical Decisions Log

## ADR-001: Modular Monolith Architecture
*   **Status:** Accepted
*   **Context:** System requires distinct components (Ingestion, Storage, Analytics) but team size and scale do not justify Microservices complexity.
*   **Decision:** Use Django Modular Monolith pattern with strict folder-based boundaries in `apps/`.
*   **Consequences:** Easier deployment/testing. Requires discipline to avoid coupling.

## ADR-002: TimescaleDB for Telemetry
*   **Status:** Accepted
*   **Context:** We need to store high-frequency sensor data and perform time-window queries efficiently.
*   **Decision:** Use TimescaleDB extension on PostgreSQL.
*   **Consequences:** optimized storage (compression) and faster time-series queries. Requires specific Docker image.

## ADR-003: Best-Effort Ingestion Strategy
*   **Status:** Accepted
*   **Context:** Network interruptions with ISS telemetry are possible. Backfilling requires complex historical API logic.
*   **Decision:** Adopt "Best Effort" strategy. Auto-reconnect on drop, accept data gaps.
*   **Consequences:** Simplifies Ingestion service significantly. No historical fetch logic needed.

## ADR-004: Polling-Based Analytics
*   **Status:** Accepted
*   **Context:** Real-time stream processing (e.g., Kafka Streams) is overkill for event detection latency requirements (~1-5 mins).
*   **Decision:** Use Celery Beat to poll the database every N seconds for new patterns.
*   **Consequences:** Decouples Ingestion from Analytics. Increases DB read load (mitigated by TimescaleDB efficiency).

## ADR-005: Single-Node Deployment via Coolify
*   **Status:** Accepted
*   **Context:** Initial scale is small/predictable. Complexity of K8s is unwarranted.
*   **Decision:** Deploy all services via Docker Compose on a single node managed by Coolify.
*   **Consequences:** Simple ops. Single point of failure (VPS).
