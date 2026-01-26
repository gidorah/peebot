# Project Roadmap: PeeBot System

**Status**: Phase 1 Refactoring (Stability & Architecture Alignment).

## Refactoring Tasks (Priority)

These tasks address architectural changes and bugs in the **currently implemented** code (`apps/core` and `apps/telemetry_storage`).

- [ ] **Refactor (Storage)**: Update `TelemetryReading` unique constraint.
    - *Goal*: Change from `(id, timestamp)` to `(channel, timestamp)` for deterministic deduplication.
    - *Files*: `apps/telemetry_storage/models.py`.

- [ ] **Fix (Core)**: Resolve `timezone.datetime` attribute error.
    - *Goal*: Replace incorrect `timezone.datetime` usage with `timezone.now()` or `datetime` module.
    - *Files*: `apps/core/models.py`.

- [ ] **Fix (Core)**: Resolve `deleted_at` field obscuration.
    - *Goal*: Fix duplicate/conflicting field definitions in base models.
    - *Files*: `apps/core/models.py`.

- [ ] **Fix (Storage)**: Resolve `Meta` class inheritance conflicts.
    - *Goal*: Ensure `TelemetryReading.Meta` correctly overrides/inherits from base model Meta classes to satisfy MRO.
    - *Files*: `apps/telemetry_storage/models.py`.

## Phase 2: Ingestion Implementation

- [ ] **Implement (Ingestion)**: Create Enrichment Service (`enricher.py`).
    - *Goal*: Move timestamp normalization and year-rollover logic from management command to a dedicated service.
    - *Files*: `apps/telemetry_ingestion/services/enricher.py`.

- [ ] **Refactor (Ingestion)**: Update Validation Layer (Pydantic).
    - *Goal*: Replace DRF Serializer with Pydantic model for high-performance ingestion (ADR-004). Integrate into `run_lightstreamer` loop.
    - *Files*: `apps/telemetry_ingestion/services/validator.py`, `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`.
