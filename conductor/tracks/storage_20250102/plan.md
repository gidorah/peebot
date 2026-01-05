# Track Plan: Implement Telemetry Storage Module

## Phase 1: Models & Migrations
- [x] Task: Create TelemetryChannel Model
    - [x] Subtask: Write failing test for TelemetryChannel creation checking all fields from spec (`public_pui`, `ops_nom`, `eng_nom`, etc.) (TDD).
    - [x] Subtask: Implement TelemetryChannel model with correct schema from `ISS Telemetry Data Analytics System.md`.
    - [x] Subtask: Verify tests pass.
- [x] Task: Create TelemetryReading Model
    - [x] Subtask: Write failing test for TelemetryReading creation (TDD).
    - [x] Subtask: Implement TelemetryReading model using **UUIDv7** for `id` (PK) and explicit `timestamp` field. Include optional status fields (`status_class`, `status_indicator`, `status_color`).
    - [x] Subtask: Verify tests pass.
- [x] Task: Configure TimescaleDB Hypertable
    - [x] Subtask: Create custom migration to convert TelemetryReading table to Hypertable.
    - [x] Subtask: Add migration for compression policy (7 days).
    - [x] Subtask: Add migration for retention policy (30 days).
    - [x] Subtask: Add migration for indexes (channel, timestamp DESC) and (ingested_at).
- [x] Task: Conductor - User Manual Verification 'Phase 1: Models & Migrations' (Protocol in workflow.md)

## Phase 2: Seeding & Data Population
- [x] Task: Create Seeding Command
    - [x] Subtask: Implement `apps/telemetry_storage/management/commands/seed_channels.py`.
    - [x] Subtask: Logic to parse `docs/PUIList.xml` and map XML tags to model fields (`Public_PUI` -> `public_pui`, `OPS_NOM` -> `ops_nom`, etc.).
    - [x] Subtask: Logic to set `is_active=True` ONLY for `NODE3000004`, False for others (Implemented via `SoftDeleteModel.deleted_at`).
    - [x] Subtask: Logic to update existing records (idempotency).
- [x] Task: Test Seeding Command
    - [x] Subtask: Write test case verifying all channels are imported with correct field mapping.
    - [x] Subtask: Write test case verifying only UPA is active.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Seeding & Data Population' (Protocol in workflow.md)

## Phase 3: Repository Layer
- [x] Task: Implement TelemetryRepository Interface
    - [x] Subtask: Define the abstract base class or interface.
    - [x] Subtask: Implement `get_active_channels` method.
- [x] Task: Implement Bulk Ingestion
    - [x] Subtask: Write failing test for bulk ingestion performance/correctness (TDD).
    - [x] Subtask: Implement `abulk_create_readings` method in repository using async ORM (Uses `ReadingData` DTO for decoupling).
    - [x] Subtask: Verify tests pass.
- [x] Task: Conductor - User Manual Verification 'Phase 3: Repository Layer' (Protocol in workflow.md)

## Phase 4: Integration & Cleanup
- [x] Task: Expose Public API
    - [x] Subtask: Define `__all__` in `apps/telemetry_storage/__init__.py` (Note: Kept minimal to avoid AppRegistryNotReady errors).
- [x] Task: Final Polish
    - [x] Subtask: Run full test suite and ensure >80% coverage.
    - [x] Subtask: Run mypy and ruff.
- [x] Task: Conductor - User Manual Verification 'Phase 4: Integration & Cleanup' (Protocol in workflow.md)
