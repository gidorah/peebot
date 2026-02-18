# Requirements: T004 - Duplicate Reading Prevention

## 1. Goal

Prevent duplicate `TelemetryReading` rows from being inserted into the database, particularly on service restart when Lightstreamer re-broadcasts the latest snapshot values for all subscribed channels.

## 2. Background

On service restart, the Lightstreamer client re-subscribes to all channels and immediately receives the current (latest) value for each. These values carry the same timestamp as readings already persisted from the previous session, creating `(channel, timestamp)` duplicates. There are two compounding defects in the current implementation:

1. **Useless unique constraint**: `TelemetryReading` has `UniqueConstraint(fields=["id", "timestamp"])`. Since `id` is a UUIDv7 (always unique per row), this constraint never blocks any insert. It provides zero deduplication.
2. **No conflict handling on insert**: The live ingestion path in `run_lightstreamer.py` calls `abulk_create(readings)` without `ignore_conflicts=True`. If a genuine constraint violation did occur, it would raise an `IntegrityError`, silently dropping the entire batch via the broad `except Exception` handler.

## 3. Functional Requirements

### 3.1 Database Constraint (FR-DEDUP-001)
1. The system shall enforce that at most one `TelemetryReading` row exists per `(channel, timestamp)` pair.
2. The existing `UniqueConstraint(fields=["id", "timestamp"])` shall be replaced with `UniqueConstraint(fields=["channel", "timestamp"])`.
3. The new constraint name shall be `unique_channel_timestamp`.

### 3.2 Ingestion Conflict Handling (FR-DEDUP-002)
1. The bulk insert in `run_lightstreamer.py` shall pass `ignore_conflicts=True` to `abulk_create`.
2. On service restart, duplicate readings (same `channel` + `timestamp` as an existing row) shall be silently skipped — no error, no batch abort.
3. Genuinely new readings arriving in the same batch as duplicates shall still be persisted.

### 3.3 No Data Loss (FR-DEDUP-003)
1. The fix shall not drop valid, non-duplicate readings.
2. The first insert of a `(channel, timestamp)` pair shall always succeed.

## 4. Non-Functional Requirements

### 4.1 Compatibility with TimescaleDB (NFR-DEDUP-001)
1. All unique indexes on `TelemetryReading` must include the hypertable partition key (`timestamp`). The new `(channel_id, timestamp)` constraint satisfies this requirement.
2. The migration must not break the composite primary key `(id, timestamp)` established by `0002_timescaledb.py`.

### 4.2 Architecture (NFR-DEDUP-002)
1. The ingestion fix (FR-DEDUP-002) shall be applied at the ORM call site in `run_lightstreamer.py`. It does not require wiring through `DjangoTelemetryRepository` (Option B chosen).
2. `DjangoTelemetryRepository.abulk_create_readings` already uses `ignore_conflicts=True` and requires no changes.

### 4.3 Performance (NFR-DEDUP-003)
1. The `ignore_conflicts=True` path in PostgreSQL uses an `ON CONFLICT DO NOTHING` clause. This has negligible overhead for the normal (non-duplicate) case.
2. The new composite index on `(channel_id, timestamp)` doubles as the deduplication enforcement index and benefits the existing query pattern in `tasks.py` (which filters by `channel__public_pui` and orders by `timestamp`).

## 5. Constraints

1. The migration must be safe to run against a live TimescaleDB hypertable (C-001).
2. No changes to the two-pointer sliding window algorithm in `pee_bot.py` are required. Once the DB constraint is in place, the query in `tasks.py` is guaranteed to return at most one reading per timestamp for a given channel (C-002).

## 6. Assumptions

1. The Lightstreamer telemetry system may legitimately emit two different values for the same channel at the same timestamp (sensor noise). With `ignore_conflicts=True`, the first-written value wins and the second is discarded. This is acceptable (A-001).
2. Existing duplicate rows (if any) in production are not cleaned up as part of this task. The constraint prevents new duplicates going forward (A-002).
