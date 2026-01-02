# Track Plan: Implement Telemetry Storage Module

## Phase 1: Models & Migrations
- [ ] Task: Create TelemetryChannel Model
    - [ ] Subtask: Write failing test for TelemetryChannel creation checking all fields from spec (`public_pui`, `ops_nom`, `eng_nom`, etc.) (TDD).
    - [ ] Subtask: Implement TelemetryChannel model with correct schema from `ISS Telemetry Data Analytics System.md`.
    - [ ] Subtask: Verify tests pass.
- [ ] Task: Create TelemetryReading Model
    - [ ] Subtask: Write failing test for TelemetryReading creation (TDD).
    - [ ] Subtask: Implement TelemetryReading model using **UUIDv7** for `id` (PK) and explicit `timestamp` field. Include optional status fields (`status_class`, `status_indicator`, `status_color`).
    - [ ] Subtask: Verify tests pass.
- [ ] Task: Configure TimescaleDB Hypertable
    - [ ] Subtask: Create custom migration to convert TelemetryReading table to Hypertable.
    - [ ] Subtask: Add migration for compression policy (7 days).
    - [ ] Subtask: Add migration for retention policy (30 days).
    - [ ] Subtask: Add migration for indexes (channel, timestamp DESC) and (ingested_at).
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Models & Migrations' (Protocol in workflow.md)

## Phase 2: Seeding & Data Population
- [ ] Task: Create Seeding Command
    - [ ] Subtask: Implement `apps/telemetry_storage/management/commands/seed_channels.py`.
    - [ ] Subtask: Logic to parse `docs/PUIList.xml` and map XML tags to model fields (`Public_PUI` -> `public_pui`, `OPS_NOM` -> `ops_nom`, etc.).
    - [ ] Subtask: Logic to set `is_active=True` ONLY for `NODE3000004`, False for others.
    - [ ] Subtask: Logic to update existing records (idempotency).
- [ ] Task: Test Seeding Command
    - [ ] Subtask: Write test case verifying all channels are imported with correct field mapping.
    - [ ] Subtask: Write test case verifying only UPA is active.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Seeding & Data Population' (Protocol in workflow.md)

## Phase 3: Repository Layer
- [ ] Task: Implement TelemetryRepository Interface
    - [ ] Subtask: Define the abstract base class or interface.
    - [ ] Subtask: Implement `get_active_channels` method.
- [ ] Task: Implement Bulk Ingestion
    - [ ] Subtask: Write failing test for bulk ingestion performance/correctness (TDD).
    - [ ] Subtask: Implement `abulk_create_readings` method in repository using async ORM.
    - [ ] Subtask: Verify tests pass.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Repository Layer' (Protocol in workflow.md)

## Phase 4: Integration & Cleanup
- [ ] Task: Expose Public API
    - [ ] Subtask: Define `__all__` in `apps/telemetry_storage/__init__.py`.
- [ ] Task: Final Polish
    - [ ] Subtask: Run full test suite and ensure >80% coverage.
    - [ ] Subtask: Run mypy and ruff.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Integration & Cleanup' (Protocol in workflow.md)
