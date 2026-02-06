# AGENT: EVENT PROCESSORS

**Module:** `apps/event_processors`
**Role:** THE BRAIN. Runs periodic analytics on stored telemetry to detect high-level events.

## CONTEXT
Independent analytics engine. Decoupled from ingestion by a **Polling Architecture**. It queries TimescaleDB on its own schedule to find patterns (e.g., UPA tank level trends).

## OWNERSHIP
- **Models**: `DetectedEvent` (Results), `ProcessorState` (Last run tracking).
- **Logic**: Sliding Window analysis, trend detection, external triggers (Bluesky).

## ARCHITECTURE: POLLING PATTERN
1. **Trigger**: Celery Beat runs task (e.g., every 30s for PeeBot).
2. **State**: Check `ProcessorState` for `last_processed_at`.
3. **Query**: Fetch `TelemetryReading` (from `storage`) since last run.
4. **Window**: Analyze sliding window (e.g., last 10m of readings).
5. **Detect**: If pattern matches, create `DetectedEvent`.
6. **Act**: Trigger external services (e.g., `bluesky_client`).
7. **Update**: Mark current time in `ProcessorState`.

## KEY COMPONENTS (PLANNED)
- `processors/`: Strategy-based detector classes (e.g., `PeeBotProcessor`).
- `tasks.py`: Celery tasks orchestrating the polling logic.
- `services/`: `BlueskyClient` for notifications.

## STATUS: SCAFFOLDING
- Infrastructure (Celery/Beat) is ready.
- Logic is documented but implementation is **PENDING**.
- Models defined in `docs/ISS Telemetry Data Analytics System.md`.

## DEPENDENCIES
- `telemetry_storage`: Source of telemetry readings.
- `core`: Base models and utilities.
