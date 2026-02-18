# Implementation Plan: T004 - Duplicate Reading Prevention

## Phase 1: Storage Layer — Fix Unique Constraint

- [x] **Step 1**: Update `TelemetryReading` unique constraint in model.
    - *File*: `apps/telemetry_storage/models.py`
    - *Task*: In the `Meta.constraints` list, replace `UniqueConstraint(fields=["id", "timestamp"], name="unique_id_timestamp")` with `UniqueConstraint(fields=["channel", "timestamp"], name="unique_channel_timestamp")`.
    - *Verification*: `uv run python manage.py check` passes. ✓

- [x] **Step 2**: Generate and review migration.
    - *Command*: `uv run python manage.py makemigrations telemetry_storage --name fix_unique_constraint`
    - *Task*: Inspect the generated migration. Confirm it:
        1. Removes `unique_id_timestamp`. ✓
        2. Adds `unique_channel_timestamp` on `(channel_id, timestamp)`. ✓
        3. Does **not** touch the composite primary key `(id, timestamp)` from `0002_timescaledb.py`. ✓
    - *Note*: TimescaleDB requires all unique indexes to include the partition column (`timestamp`). `(channel_id, timestamp)` satisfies this.
    - *Verification*: Migration file `0004_fix_unique_constraint.py` looks correct. Apply with `uv run python manage.py migrate` when stack is live.

## Phase 2: Ingestion Layer — Add Conflict Handling

- [ ] **Step 3**: Add `ignore_conflicts=True` to the bulk insert in the ingestion command.
    - *File*: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py` (line ~252)
    - *Task*: Change `await TelemetryReading.objects.abulk_create(readings)` to `await TelemetryReading.objects.abulk_create(readings, ignore_conflicts=True)`.
    - *Verification*: Code review confirms no other `abulk_create` calls in the ingestion path are missing `ignore_conflicts`.

## Phase 3: Tests

- [ ] **Step 4**: Add constraint enforcement test.
    - *File*: `apps/telemetry_storage/tests/test_models.py`
    - *Task*: Add a test that creates one `TelemetryReading` and then attempts to insert a second row with the same `channel` and `timestamp`. Assert that `IntegrityError` is raised.
    - *Verification*: `just test` passes.

- [ ] **Step 5**: Add duplicate-skip test for bulk insert.
    - *File*: `apps/telemetry_storage/tests/test_repositories.py` (or new `test_deduplication.py`)
    - *Task*: Add a test that calls `abulk_create` (or `TelemetryReading.objects.abulk_create(..., ignore_conflicts=True)`) with two readings sharing the same `(channel, timestamp)`. Assert only one row is persisted and no exception is raised.
    - *Verification*: `just test` passes.

- [ ] **Step 6**: Add restart-simulation test for the ingestion command.
    - *File*: `apps/telemetry_ingestion/tests/` (new test file or extend existing)
    - *Task*: Simulate a restart scenario: flush a batch containing a reading for `(channel=X, timestamp=T)`, then flush a second batch containing the same reading. Assert the DB contains exactly one row for `(channel=X, timestamp=T)` after both flushes. Assert no exception is raised during either flush.
    - *Verification*: `just test` passes.

## Phase 4: Documentation

- [ ] **Step 7**: Mark roadmap item complete.
    - *File*: `docs/system-solution/main-tasks.md`
    - *Task*: Change `- [ ] **Refactor (Storage)**: Update TelemetryReading unique constraint.` to `- [x]` and add a completion date.
