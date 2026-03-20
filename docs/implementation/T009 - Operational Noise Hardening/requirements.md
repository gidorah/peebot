# Requirements: T009 - Operational Noise Hardening

## 1. Objective

Reduce false-positive Sentry issue creation for transient operational failures while preserving recovery behavior and observability.

## 2. Scope

This task covers:

- transient database disconnect handling in `run_lightstreamer.flush_buffer()`;
- log-level behavior for retryable ingestion database failures;
- regression tests for stale-connection recovery and non-error logging.

This task does not cover:

- changes to Sentry global configuration;
- broader ingestion retry redesign;
- non-ingestion operational alerts.

## 3. Functional Requirements

- FR-ONH-001: `flush_buffer()` shall close stale Django DB connections when `TelemetryReading.objects.abulk_create()` raises `OperationalError`.
- FR-ONH-002: The transient `OperationalError` path shall log at `WARNING` level, not `ERROR`, so routine disconnects do not create Sentry issues.
- FR-ONH-003: `flush_buffer()` shall continue to acknowledge all queued items in a `finally` block even when the DB write fails.
- FR-ONH-004: Non-`OperationalError` exceptions in `flush_buffer()` shall continue to log at `ERROR` level for investigation.

## 4. Constraints

- C-ONH-001: The implementation must preserve the existing ingestion buffering and queue-drain semantics from ADR-008.
- C-ONH-002: The recovery path must use Django's `close_old_connections()` through `sync_to_async(..., thread_sensitive=True)` to match async ORM thread usage.
- C-ONH-003: Tests should be narrowly scoped and avoid requiring a full database-backed integration path when mocking the failing write is sufficient.

## 5. Success Criteria

- A transient DB disconnect in `flush_buffer()` closes stale connections and does not emit an `ERROR` log.
- Existing non-DB failure behavior remains unchanged.
- Focused tests for the ingestion command pass locally.
