# Migration Reset Plan: Clean Slate

**Date:** 2026-02-18
**Context:** Pre-production. No live users, no production DB to protect. DB wipe approved.

## Why

Current migration history across `telemetry_storage` (4 files) and `event_processors`
(4 files) reflects schema evolution through mistakes rather than correct final state:

- `telemetry_storage` 0001 creates `TelemetryReading` with a wrong constraint
  (`unique_id_timestamp`) and a `deleted_at` field — both corrected by later migrations
- `event_processors` 0001 creates models with wrong field names, wrong nullability,
  and missing fields — all corrected by migrations 0002–0004

On every fresh environment (CI, new dev, staging), Django replays all these wrong
intermediate states before arriving at the correct schema. That is unnecessary
complexity that will live forever.

**Goal:** One correct initial migration per app, reflecting the models exactly as they
are today. Nothing more.

---

## Target State

| App                   | Before       | After                                    |
| --------------------- | ------------ | ---------------------------------------- |
| `telemetry_storage`   | 4 migrations | 2 (`0001_initial`, `0002_timescaledb`)   |
| `event_processors`    | 4 migrations | 1 (`0001_initial`)                       |
| `core`                | 0 migrations | unchanged                                |
| `telemetry_ingestion` | 0 migrations | unchanged                                |
| `dashboards`          | 0 migrations | unchanged                                |

---

## Execution Steps

### Step 1 — Tear down the stack and destroy the data volume

```bash
just dev-down
docker volume rm peebot_postgres_data_dev
```

`dev-down` removes containers. The named volume `peebot_postgres_data_dev` must be
removed explicitly — `--remove-orphans` does not touch volumes.

---

### Step 2 — Delete all numbered migration files

Keep every `__init__.py`. Delete only the numbered files.

**`apps/telemetry_storage/migrations/`**
- `0001_initial_v2.py`
- `0002_timescaledb.py`
- `0003_remove_telemetryreading_deleted_at.py`
- `0004_fix_unique_constraint.py`

**`apps/event_processors/migrations/`**
- `0001_create_event_processor_models.py`
- `0002_add_socialpost_status.py`
- `0003_alter_detectedevent_confidence_and_more.py`
- `0004_rename_last_processed_at_processorstate_last_processed_timestamp.py`

---

### Step 3 — Regenerate `telemetry_storage` initial migration

```bash
uv run --env-file .env.local python manage.py makemigrations telemetry_storage --name initial
```

Produces `0001_initial.py` with the current correct schema:
- `TelemetryChannel` (with `SoftDeleteModel` fields, no `is_active`)
- `TelemetryReading` (no `deleted_at`, correct `unique_channel_timestamp` constraint,
  correct indexes)

---

### Step 4 — Manually recreate `0002_timescaledb.py`

Cannot be auto-generated (hand-written `RunSQL`). Copy the current file verbatim,
updating only the `dependencies` line:

```python
# Before:
dependencies = [("telemetry_storage", "0001_initial_v2")]

# After:
dependencies = [("telemetry_storage", "0001_initial")]
```

The `reverse_sql` is intentionally incomplete (removes policies only, does not undo
the hypertable or composite PK). This is a deliberate decision from commit a8c6a3d —
the rollback strategy for TimescaleDB infrastructure is always a volume wipe, not
`migrate zero`. Leave it unchanged.

---

### Step 5 — Regenerate `event_processors` initial migration

```bash
uv run --env-file .env.local python manage.py makemigrations event_processors --name initial
```

Produces `0001_initial.py` with all three models in their correct final state:
- `DetectedEvent` (nullable `confidence`, correct index)
- `ProcessorState` (`last_processed_timestamp`, not `last_processed_at`)
- `SocialPost` (with `status`, `error_message`, nullable `posted_at`, correct indexes)

---

### Step 6 — Verify no pending changes

```bash
uv run --env-file .env.local python manage.py makemigrations --check
```

Must exit 0 (no model changes unaccounted for by the new migrations). If it detects
drift, stop and investigate before continuing.

---

### Step 7 — Bring infrastructure up and migrate

Start only the DB services first:

```bash
just dev-up timescaledb pgbouncer
```

Wait for healthchecks, then apply migrations directly (bypassing PgBouncer to avoid
the 30s `query_timeout` on the TimescaleDB `RunSQL` block in `0002_timescaledb`):

```bash
just dev-migrate-direct
```

---

### Step 8 — Seed reference data

Re-populate `TelemetryChannel` rows (lost with the volume wipe):

```bash
just dev-python manage.py seed_channels
```

---

### Step 9 — Bring the full stack up

```bash
just dev-up
```

---

### Step 10 — Smoke test

```bash
just test
```

All tests must pass against the fresh DB and clean migrations.

---

## Notes

- `0002_timescaledb.py` is the only hand-authored migration in the entire codebase.
  All others are generated. Keep it that way.
- Future migrations that involve bulk DML, index builds, or TimescaleDB decompression
  must use `just dev-migrate-direct`, not `just dev-migrate`. This is documented in
  the Justfile.
- `just dev-migrate` (PgBouncer path) remains the default for routine migrations —
  it is fine for all standard Django DDL operations.
