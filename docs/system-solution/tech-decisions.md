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
