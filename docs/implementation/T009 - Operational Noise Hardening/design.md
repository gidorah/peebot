# Design: T009 - Operational Noise Hardening

## 1. Overview

`run_lightstreamer.flush_buffer()` already owns the ingestion batch write boundary, so the fix stays there. The initial ingestion recovery change correctly added stale-connection cleanup for `OperationalError`, but it still logged that transient failure at `ERROR` level. Because PeeBot's Sentry setup creates issues from Python `ERROR+` logs, that behavior still produced the exact operational noise this task is meant to remove.

## 2. Approach

The design keeps the new dedicated `except OperationalError` branch and changes only its log level from `error` to `warning`. This mirrors the retryable database handling already used in `apps/event_processors/tasks.py`: transient DB failures should remain visible in logs but should not create Sentry issues before the system has a chance to recover on the next flush cycle.

The general `except Exception` branch remains at `ERROR` because unexpected failures in ingestion transformation or command logic are not known-transient and should still page through normal error reporting.

## 3. Test Strategy

Extend `apps/telemetry_ingestion/tests/test_run_lightstreamer_command.py` with one additional focused unit test that patches the module logger and asserts:

- `OperationalError` triggers `logger.warning(...)`;
- `logger.error(...)` is not called for that path.

The existing tests for `close_old_connections()` and queue acknowledgements remain valid and continue to verify recovery semantics.
