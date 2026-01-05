# AGENT CONTEXT: telemetry_storage

**Role**: Single Source of Truth (SSoT) for ISS telemetry data.
**Ownership**: `TelemetryChannel`, `TelemetryReading`.

## ARCHITECTURE
- **Pattern**: Repository Pattern. DO NOT access models directly from other modules; use `apps.telemetry_storage.repositories`.
- **Database**: TimescaleDB. `TelemetryReading` is a hypertable.
- **Dependency Flow**: `telemetry_ingestion` (Writer) -> `telemetry_storage` (Owner) <- `event_processors` (Reader).

## MODELS (MATCH README SPEC)
1. **TelemetryChannel**:
   - `public_pui`: Unique ISS identifier (e.g., 'NODE3000004').
   - Metadata: `description`, `ops_nom`, `eng_nom`, `unit`.
   - **Active State**: Managed via `SoftDeleteModel`. Active = `deleted_at IS NULL`.
2. **TelemetryReading**:
   - Time-series data: `timestamp` (Primary Partition Key), `value`, `calibrated_data`.
   - Traceability: `id` (UUIDv7), `created_at` (Ingestion Time), `metadata` (JSONB).
   - Relations: `channel` (ForeignKey to TelemetryChannel).

## TIMESCALEDB SCHEMA (MANDATORY)
- **Hypertable**: `create_hypertable('telemetry_reading', 'timestamp')`.
- **Chunks**: 1-day intervals.
- **Compression**: Enabled after 7 days (Segment by `channel_id`).
- **Retention**: Drop chunks older than 30 days.

## IMPLEMENTATION STATUS
- **Status**: IN_PROGRESS.
- **Tasks**:
  1. [x] Define `TelemetryChannel` and `TelemetryReading` in `models.py`.
  2. [x] Implement `seed_channels` command to populate channels from XML.
  3. [ ] Implement `repositories.py` with `abulk_create` support.
  4. [ ] Create migration with `RunSQL` for TimescaleDB setup (hypertables/compression).

## DEV COMMANDS
- `uv run python manage.py makemigrations telemetry_storage`
- `uv run python manage.py migrate`
- `uv run python manage.py dbshell` (Check hypertable status via `\dx`)
