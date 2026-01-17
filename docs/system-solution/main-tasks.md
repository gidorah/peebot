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
