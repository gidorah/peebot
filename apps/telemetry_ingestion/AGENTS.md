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
- `validator.py`: (Pending) DRF-based validation of incoming telemetry packets.
- `identifiers.py`: Single source for subscribed ISS Item IDs.

## INTEGRATION POINTS
- **Input**: Lightstreamer `MERGE` mode subscription.
- **Output**: Bulk inserts into `TelemetryReading` (via `telemetry_storage` repo).

## CURRENT STATUS: SCAFFOLDING
- **DONE**: Client connection and "Async Bridge" pattern verified.
- **PENDING**: 
    - Data enrichment (mapping Item IDs to `TelemetryChannel` IDs).
    - Validation logic (handling malformed stream data).
    - High-performance bulk storage implementation.

## DEV COMMANDS
```bash
uv run python manage.py run_lightstreamer
```
