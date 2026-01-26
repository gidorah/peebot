# Implementation Plan: Ingestion Validation & Enrichment

## Phase 1: Preparation
- [ ] **Step 1**: Install Pydantic (if not already present/updated) and verify environment.
    - *Command*: `uv pip install pydantic` (or check pyproject.toml).
    - *Verification*: `python -c "import pydantic; print(pydantic.VERSION)"`

## Phase 2: Implementation
- [ ] **Step 2**: Implement Validation Service.
    - *File*: `apps/telemetry_ingestion/services/validator.py`
    - *Task*: Replace existing DRF serializer with `LightstreamerReading` Pydantic model. Implement `validate_payload` helper.
    - *Test*: Add unit test `tests/test_validator.py`.

- [ ] **Step 3**: Implement Enrichment Service.
    - *File*: `apps/telemetry_ingestion/services/enricher.py`
    - *Task*: Create `TelemetryEnricher` class with timestamp normalization logic.
    - *Test*: Add unit test `tests/test_enricher.py` (specifically testing rollover logic).

- [ ] **Step 4**: Integrate into Management Command.
    - *File*: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`
    - *Task*:
        - Import new services.
        - Refactor `ingestion_worker` to use `validator` and `enricher`.
        - Refactor `flush_buffer` to only handle `abulk_create` (remove logic).

## Phase 3: Verification
- [ ] **Step 5**: Run Unit Tests.
    - *Command*: `pytest apps/telemetry_ingestion/tests/`
- [ ] **Step 6**: Manual Dry Run.
    - *Command*: `python manage.py run_lightstreamer` (ensure it starts without error and connects).
