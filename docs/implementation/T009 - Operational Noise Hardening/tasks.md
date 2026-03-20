# Tasks: T009 - Operational Noise Hardening

## Phase 1: Spec alignment

- [x] Add implementation docs for requirements, design, and tasks.
- [x] Update `docs/system-solution/main-tasks.md` with the T009 roadmap entry before code changes.
- [x] Confirm the fix aligns with ADR-008 queue safety and existing retryable DB error handling patterns.

## Phase 2: Ingestion hardening

- [x] Downgrade transient `OperationalError` logging in `run_lightstreamer.flush_buffer()` from `ERROR` to `WARNING`.
- [x] Preserve stale-connection cleanup via `close_old_connections()`.
- [x] Keep the generic exception path unchanged.

## Phase 3: Verification

- [x] Add a regression test proving the `OperationalError` path logs at warning level.
- [x] Run the focused ingestion command tests locally.
