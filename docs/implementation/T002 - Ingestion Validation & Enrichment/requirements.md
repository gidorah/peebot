# Requirements: Ingestion Validation & Enrichment

## 1. Overview
Refactor the existing ad-hoc ingestion logic in `run_lightstreamer.py` into dedicated, high-performance services. This task unifies the **Validation Layer** (replacing DRF with Pydantic per ADR-004) and the **Enrichment Layer** (centralizing timestamp normalization per ADR-007).

The goal is to ensure the "hot path" of telemetry ingestion is robust, testable, and capable of handling 10,000 messages/second without CPU bottlenecks.

## 2. Functional Requirements

### 2.1 Validation Service
*   **REQ-VAL-001**: The system must validate raw incoming dictionary data against a strict schema using **Pydantic V2**.
*   **REQ-VAL-002**: Required fields:
    *   `PUI` (derived from item name key).
    *   `Value` (must be present; status-only updates are dropped).
*   **REQ-VAL-003**: Optional fields (pass-through if valid, ignore if missing):
    *   `TimeStamp` (Hours since start of year).
    *   `Status` dictionary (`Class`, `Indicator`, `Color`).
*   **REQ-VAL-004**: The validator must reject malformed data (e.g., non-numeric values where numbers are expected) before it reaches the enrichment phase.

### 2.2 Enrichment Service
*   **REQ-ENR-001**: The system must convert the Lightstreamer `TimeStamp` (float: "Hours since start of year") into a valid, timezone-aware UTC `datetime` object.
    *   *Business Logic*: Base date is **Dec 31 of the previous year** (0.0 hours = Start of Jan 1).
*   **REQ-ENR-002**: The system must detect and handle **Year Rollover** edge cases.
    *   *Scenario*: Processing data labeled with the previous year's "hours" while the server clock has just crossed into the new year.
    *   *Logic*: If the calculated timestamp is > 24 hours in the future relative to server time, it belongs to the previous year.
*   **REQ-ENR-003**: The system must convert the string `Value` field into a Python `Decimal` with appropriate precision.
*   **REQ-ENR-004**: If the source `TimeStamp` is missing or invalid, the system must default to the current server time (`timezone.now()`).

### 2.3 Integration
*   **REQ-INT-001**: The `run_lightstreamer` management command must be updated to use these new services in its consumer loop (`ingestion_worker`).
*   **REQ-INT-002**: The ad-hoc validation and date parsing logic currently inside `flush_buffer` must be removed.

## 3. Non-Functional Requirements

### 3.1 Performance
*   **NFR-PERF-001**: The combined Validation + Enrichment overhead must remain negligible to support **10,000 messages/second**.
    *   *Constraint*: Use `Pydantic` (compiled CoreSchema) instead of Django REST Framework.
    *   *Constraint*: Avoid DB lookups in the hot path (rely on the pre-loaded Channel Map).

### 3.2 Resilience
*   **NFR-REL-001**: Validation or Enrichment failures must **never crash the ingestion loop**.
    *   *Action*: Invalid items are logged (at WARNING/ERROR level depending on severity) and dropped.
    *   *Metric*: The system must continue processing subsequent items in the buffer immediately.

## 4. Constraints
*   **C-001**: Do not use `serializers.Serializer` (DRF) for the ingestion pipeline.
*   **C-002**: Do not modify the `TelemetryReading` database model in this task (schema is fixed).
*   **C-003**: Maintain `sync_to_async` boundaries strictly; services should be pure Python (CPU-bound) and not require async IO.
