# Telemetry Ingestion Module Implementation Tasks

## Phase 1: Storage Layer Preparation
- [ ] Create the `TelemetryRepository` class structure.
  - **File**: `apps/telemetry_storage/repositories.py`
- [ ] Implement the `get_active_channels` method to fetch channels where `is_active=True` (async).
  - **File**: `apps/telemetry_storage/repositories.py`
- [ ] Implement the `bulk_create_readings` method using `abulk_create` with `ignore_conflicts=True`.
  - **File**: `apps/telemetry_storage/repositories.py`

## Phase 2: Validation & Enrichment
- [ ] Create the `IngestTelemetrySerializer` class inheriting from DRF `Serializer`.
  - **File**: `apps/telemetry_ingestion/serializers.py`
- [ ] Define serializer fields: `item_id`, `timestamp`, `value`, `status`.
  - **File**: `apps/telemetry_ingestion/serializers.py`
- [ ] Implement validation logic for timestamp sanity (future/past checks).
  - **File**: `apps/telemetry_ingestion/serializers.py`
- [ ] Create the `EnrichmentService` class.
  - **File**: `apps/telemetry_ingestion/services/enricher.py`
- [ ] Implement the `enrich` method to add `uuid`, `ingested_at`, and normalize keys.
  - **File**: `apps/telemetry_ingestion/services/enricher.py`
- [ ] Add unit tests for `IngestTelemetrySerializer` validation edge cases.
  - **File**: `apps/telemetry_ingestion/tests/test_serializers.py`
- [ ] Add unit tests for `EnrichmentService` logic.
  - **File**: `apps/telemetry_ingestion/tests/test_enricher.py`

## Phase 3: Lightstreamer Client Service
- [ ] Define the `LightstreamerService` class structure.
  - **File**: `apps/telemetry_ingestion/services/lightstreamer_client.py`
- [ ] Implement the asynchronous connection logic with exponential backoff.
  - **File**: `apps/telemetry_ingestion/services/lightstreamer_client.py`
- [ ] Implement the `load_subscriptions` method to fetch channels via `TelemetryRepository`.
  - **File**: `apps/telemetry_ingestion/services/lightstreamer_client.py`
- [ ] Implement the `on_item_update` callback to handle incoming data stream.
  - **File**: `apps/telemetry_ingestion/services/lightstreamer_client.py`
- [ ] Wire up `IngestTelemetrySerializer` and `EnrichmentService` within `on_item_update`.
  - **File**: `apps/telemetry_ingestion/services/lightstreamer_client.py`
- [ ] Implement the internal data buffer and `flush_buffer` async task.
  - **File**: `apps/telemetry_ingestion/services/lightstreamer_client.py`
- [ ] Add unit tests for connection backoff and buffer logic (mocking external calls).
  - **File**: `apps/telemetry_ingestion/tests/test_services.py`

## Phase 4: Management Command
- [ ] Create the `run_lightstreamer.py` command file.
  - **File**: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`
- [ ] Implement the `Command` class inheriting from Django's `BaseCommand`.
  - **File**: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`
- [ ] Implement the `handle` method to initialize and run `LightstreamerService`.
  - **File**: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`
- [ ] Add signal handling for graceful shutdown (SIGINT/SIGTERM).
  - **File**: `apps/telemetry_ingestion/management/commands/run_lightstreamer.py`

## Phase 5: Integration & Verification
- [ ] Create an integration test simulating the full pipeline with mocked Lightstreamer inputs and a real Test DB.
  - **File**: `apps/telemetry_ingestion/tests/test_integration.py`
- [ ] Verify `bulk_create_readings` writes correctly to TimescaleDB in the test environment.
  - **File**: `apps/telemetry_ingestion/tests/test_integration.py`
