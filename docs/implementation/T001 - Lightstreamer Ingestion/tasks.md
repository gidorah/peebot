# Tasks: T001 - Lightstreamer Ingestion

## Phase 1: Service Implementation (`lightstreamer_client.py`)
- [x] **Field Probe**: (Priority) Create a temporary script/test to connect and print *all* available fields from an update to confirm wire names (e.g., `Status.Class` vs `StatusClass`).
- [x] **Refactor Client Service**: Rewrite `LightstreamerClientService` to accept `item_names` and `callback` in `__init__`.
- [x] **Implement SubListener**: Update `SubListener` to extract `TimeStamp`, `Value`, and `Status.*` fields and bridge them to the asyncio loop properly.
- [x] **Clean Imports**: Remove internal/haxe imports and use public API or safe reflection if necessary.

## Phase 2: Management Command Core (`run_lightstreamer.py`)
- [ ] **Channel Map Loading**: Implement `load_channel_map` to fetch `TelemetryChannel`s into a `dict[pui, uuid]`.
- [ ] **Queue Setup**: Initialize `asyncio.Queue` (size 50k) in the command.
- [ ] **Producer Callback**: Create the `on_item_update` callback to push to the queue with backpressure handling (drop oldest/warn).
- [ ] **Consumer Worker**: Implement `ingestion_worker` with the buffering logic (2000 items / 500ms flush).

## Phase 3: Ingestion Logic & Transformation
- [ ] **Data Transformation**: Implement helper to parse `timestamp` (UTC), `value` (Decimal), and resolve `channel_id`.
- [ ] **Batch Write**: Implement `flush_buffer` using `TelemetryReading.objects.abulk_create`.

## Phase 4: Resilience & Lifecycle
- [ ] **Connection Loop**: Wrap client connection in a `while` loop with exponential backoff.
- [ ] **Signal Handling**: Add `SIGINT/SIGTERM` handlers to trigger graceful shutdown.
- [ ] **Shutdown Drain**: Ensure queue is drained and final buffer is flushed on exit.

## Phase 5: Verification
- [ ] **Manual Test**: Run command and verify data appears in `TelemetryReading` table via Django Admin or `psql`.
- [ ] **Load Test**: (Optional) Use `locust` or manual injection to simulate high load and check logs for queue drops.
