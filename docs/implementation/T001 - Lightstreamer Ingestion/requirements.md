# Requirements: T001 - Lightstreamer Ingestion

## 1. Goal
Implement a robust, high-performance telemetry ingestion pipeline that connects to the ISS Lightstreamer feed, validates data, and persists it to TimescaleDB in batches.

## 2. Functional Requirements
1.  **Lightstreamer Connection**: Establish and maintain a stable connection to `http://push.lightstreamer.com` with the `ISSLIVE` adapter set.
2.  **Channel Subscription**: Subscribe to the telemetry channels defined in `apps.telemetry_ingestion.services.identifiers.IDENTIFIERS`.
3.  **Data Extraction**: Extract `TimeStamp`, `Value`, `Status.Class`, `Status.Indicator`, and `Status.Color` fields from incoming updates.
4.  **Channel Resolution**: Map incoming Item Names (e.g., "NODE3000004") to `TelemetryChannel` UUIDs using an in-memory lookup table (dictionary).
5.  **Buffered Ingestion**: 
    *   Implement an asynchronous consumer that pulls data from a thread-safe queue.
    *   Buffer readings in memory.
    *   Flush to database using `abulk_create` when the buffer reaches 2,000 items OR after 500ms has elapsed.
6.  **Resilience**:
    *   Implement exponential backoff (1s to 60s) for connection retries.
    *   Handle network drops gracefully without crashing the management command.
7.  **Graceful Shutdown**:
    *   Capture `SIGINT` and `SIGTERM`.
    *   Ensure all remaining items in the buffer are flushed to the database before the process exits.

## 3. Non-Functional Requirements
1.  **Throughput**: Must handle at least 70 msg/sec nominal and sustain bursts of 10k msg/sec.
2.  **Latency**: P99 persistence latency (from receipt to DB) must be < 5s.
3.  **Efficiency**: Minimize database round-trips via batching. Avoid redundant read queries via in-memory channel mapping (ADR-005).
4.  **Type Safety**: Ensure `timestamp` is converted to UTC `datetime` and `value` is converted to `Decimal`.

## 4. Constraints
1.  Must use `lightstreamer-client-lib` version 2.2.2.
2.  Must not use DRF serializers for ingestion validation (per ADR-004).
3.  Must follow the "Sync-to-Async Bridge" architecture using `asyncio.Queue`.
4.  Must respect module boundaries (Ingestion module imports models from Storage module).
