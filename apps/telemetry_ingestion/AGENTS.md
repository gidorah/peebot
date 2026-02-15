# AGENT CONTEXT: Telemetry Ingestion

Handles real-time stream ingestion from Lightstreamer (ISS Live Feed).

## STRICT BOUNDARIES
- **NO MODELS**: Strictly prohibited from defining Django models.
- **OWNERSHIP**: Writes to `telemetry_storage`. Owns ingestion logic only.
- **DEPENDENCY**: `telemetry_ingestion` -> `telemetry_storage`.

## CORE PATTERN: "ASYNC BRIDGE"
Connects synchronous, multi-threaded Lightstreamer SDK to Django Async loop.
- **Mechanism**: `asyncio.run_coroutine_threadsafe`.
- **Flow**: LS Thread -> `SubListener.onItemUpdate` -> `asyncio` callback -> Django Async ORM.

## PRIMARY COMPONENTS
- `run_lightstreamer`: Management command. Entry point for the async event loop.
- `LightstreamerClientService`: Orchestrates connection, subscriptions, and listener lifecycle.
- `SubListener`: The Bridge. Translates SDK callbacks into async tasks.
- `validator.py`: Pydantic V2 based validation service (`LightstreamerReading`).
- `enricher.py`: Transforms raw readings into normalized `TelemetryReading` dicts (handles Year Rollover).
- `identifiers.py`: Single source for subscribed ISS Item IDs.

## INTEGRATION POINTS
- **Input**: Lightstreamer `MERGE` mode subscription.
- **Output**: Bulk inserts into `TelemetryReading` (via `telemetry_storage` repo).

## CURRENT STATUS: STABLE
- **DONE**: Client connection and "Async Bridge" pattern.
- **DONE**: Pydantic Validation (ADR-004).
- **DONE**: Enrichment Service (ADR-007).
- **DONE**: Robust Queue Handling (Backpressure & Loop Safety).

## DEV COMMANDS
```bash
# In Docker (Automatic via just dev-up)
docker logs -f peebot_ingestion_dev

# Manual Execution
uv run python manage.py run_lightstreamer
```
