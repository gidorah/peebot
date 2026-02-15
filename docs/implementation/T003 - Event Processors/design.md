# Design: T003 - Event Processors

## 1. Overview

This module implements a polling-based analytics framework using Celery Beat. Processors independently query TimescaleDB for pattern detection and trigger actions (e.g., Bluesky posts) upon event detection.

### 1.1 Design Rationale: Why Polling?

| Concern | Polling Approach | Streaming Alternative |
|---------|------------------|----------------------|
| Sliding window analysis | Native DB query for time range | Complex stateful stream processing |
| Processor isolation | Independent schedules, no shared state | Failure propagation risk |
| Historical replay | Adjust `last_processed_timestamp` | Requires separate replay infrastructure |
| Operational complexity | Single DB as source of truth | Kafka/RabbitMQ + monitoring overhead |

## 2. Module Structure

```
apps/event_processors/
├── models.py                # DetectedEvent, ProcessorState
├── processors/
│   ├── __init__.py
│   ├── base.py              # Abstract BaseProcessor
│   └── pee_bot.py           # PeeBot implementation
├── services/
│   ├── __init__.py
│   ├── bluesky_client.py    # Bluesky API wrapper
│   └── joke_generator.py    # LLM integration
├── tasks.py                 # Celery periodic tasks
└── tests/
```

## 3. Data Models

### 3.1 DetectedEvent

Stores analytics results (e.g., detected urination events). Generic model for all processor types.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUIDv7 | PK, time-sortable (inherits `UUID7Model`) |
| `event_type` | CharField | Event category (e.g., `urination`, `temp_spike`) |
| `channel_id` | CharField | PUI of source channel (e.g., `NODE3000004`) |
| `detected_at` | DateTimeField | Logical timestamp of event occurrence |
| `confidence` | DecimalField | Detection confidence (0.0–1.0) |
| `metadata` | JSONField | Processor-specific detection details (trend data, thresholds, burst duration) |
| `created_at` | DateTimeField | Record creation (inherits `TimeStampedModel`) |

**Indexes**: `(event_type, -detected_at)` for dashboard queries.

### 3.2 ProcessorState

Maintains processor state for resumption and replay.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUIDv7 | PK, time-sortable (inherits `UUID7Model`) |
| `processor_name` | CharField | Unique processor identifier (unique constraint) |
| `last_processed_timestamp` | DateTimeField | Last successfully analyzed data timestamp |
| `last_run_at` | DateTimeField | Last execution start time |
| `state_data` | JSONField | Processor-specific state (nullable) |
| `updated_at` | DateTimeField | Last update (inherits `TimeStampedModel`) |

### 3.3 SocialPost

Tracks social media posts linked to detected events. Supports multiple platforms.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUIDv7 | PK, time-sortable (inherits `UUID7Model`) |
| `event` | ForeignKey | Reference to `DetectedEvent` |
| `platform` | CharField | Social platform (e.g., `bluesky`) |
| `external_id` | CharField | Platform-specific post ID (e.g., Bluesky post URI) |
| `content` | TextField | The posted text content |
| `posted_at` | DateTimeField | When the post was published |
| `created_at` | DateTimeField | Record creation (inherits `TimeStampedModel`) |

**Indexes**: `(platform, -posted_at)` for cooldown queries.

## 4. Component Design

### 4.1 Polling Architecture

```
┌─────────────┐     30s      ┌──────────────┐    0-5s jitter    ┌─────────────────┐
│ Celery Beat │─────────────▶│ Celery Task  │──────────────────▶│ BaseProcessor   │
└─────────────┘              └──────────────┘                   └────────┬────────┘
                                                                         │
                              ┌──────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────────────┐
              │         ProcessorState.load()         │
              │  (get last_processed_timestamp cursor)│
              └───────────────────┬───────────────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │   Query TelemetryReading for channel  │
              │   where timestamp >= cursor           │
              │   ordered by timestamp, limited to    │
              │   analysis window                     │
              └───────────────────┬───────────────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │         Processor.analyze()           │
              │   (sliding window trend detection)    │
              └───────────────────┬───────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
             [No Event]                  [Event Detected]
                    │                           │
                    │                           ▼
                    │              ┌─────────────────────────┐
                    │              │  DetectedEvent.create() │
                    │              └────────────┬────────────┘
                    │                           │
                    │                           ▼
                    │              ┌─────────────────────────┐
                    │              │  Check cooldown (30m)   │
                    │              └────────────┬────────────┘
                    │                           │
                    │              ┌────────────┴────────────┐
                    │              ▼                         ▼
                    │         [Cooldown]              [Post Allowed]
                    │              │                         │
                    │              │                         ▼
                    │              │              ┌──────────────────┐
                    │              │              │ JokeGenerator    │
                    │              │              └────────┬─────────┘
                    │              │                       │
                    │              │                       ▼
                    │              │              ┌──────────────────┐
                    │              │              │ BlueskyClient    │
                    │              │              └────────┬─────────┘
                    │              │                       │
                    └──────────────┴───────────────────────┘
                                  │
                                  ▼
              ┌───────────────────────────────────────┐
              │     ProcessorState.update_cursor()    │
              └───────────────────────────────────────┘
```

### 4.2 Jitter Strategy

All processor tasks implement a random startup delay between 0–5 seconds before executing. This prevents "thundering herd" database load spikes when multiple processors share the same schedule alignment.

### 4.3 BaseProcessor Interface

An abstract base class that all processors must inherit. Defines the contract for analytics modules.

| Method/Attribute | Description |
|------------------|-------------|
| `processor_name` | Unique string identifier for this processor |
| `channel_pui` | Target telemetry channel PUI |
| `poll_interval_seconds` | How often the processor runs |
| `window_minutes` | Size of the sliding analysis window |
| `analyze(readings)` | Analyze readings list, return detection result or None |
| `get_confidence(readings)` | Calculate and return confidence score (Decimal 0.0–1.0) |

### 4.4 PeeBot Processor

| Configuration | Default | Description |
|---------------|---------|-------------|
| Channel | `NODE3000004` | UPA Tank Level sensor |
| Poll interval | 30 seconds | How often to check for new data |
| Observation window | 5-10 minutes | How far back to query readings for context |
| Min burst duration | 30 seconds | Minimum sustained increase to qualify as fill |
| Max burst duration | 2 minutes | Expected upper bound for urination duration |
| Min delta threshold | TBD (calibration needed) | Minimum level change to filter noise |
| Stability check window | 15 seconds | Post-burst validation period |

**Detection Logic: Burst Detection with Glitch Filtering**

1. **Query**: Fetch last 5-10 minutes of readings for `NODE3000004`
2. **Detect Rising Edge**: Identify periods where level is increasing
3. **Burst Validation**: Check if increase is sustained for 30s–2min AND exceeds delta threshold
4. **Glitch Rejection**: If level reverts to baseline within ~15 seconds of increase, classify as glitch and ignore
5. **Stability Check**: After burst ends, verify level stabilizes or slowly decreases (UPA processing) rather than immediately dropping
6. **Record Event**: If validated, create `DetectedEvent` with confidence score and burst metadata (start time, duration, delta)

## 5. External Integrations

### 5.1 JokeGenerator Service

| Aspect | Detail |
|--------|--------|
| Provider | DeepSeek V3 via OpenRouter |
| Client Library | `openai` Python SDK (OpenAI-compatible API) |
| Method | `generate(event)` → returns humorous text string |
| Tone | "Dry, scientific, slightly absurd" |
| Context | Include event timestamp and confidence in prompt |
| Error Handling | Retry with exponential backoff (max 3 attempts). On failure, skip posting and log error. |

### 5.2 BlueskyClient Service

| Aspect | Detail |
|--------|--------|
| Library | atproto (AT Protocol SDK) |
| Method | `post(text)` → returns Bluesky post URI |
| Cooldown Check | Query `SocialPost` for posts within last 30 minutes before allowing new post |
| Error Handling | Log failures to Seq. Do not retry immediately (respect rate limits). |

## 6. Celery Configuration

### 6.1 Task Registration

Define a Celery task in `tasks.py` that instantiates and executes the PeeBot processor. The task handles jitter, processor execution, and state updates.

### 6.2 Beat Schedule

Register the PeeBot task in `config/celery.py` beat schedule with a 30-second interval. Task name follows the pattern `apps.event_processors.tasks.run_peebot_processor`.

## 7. Error Handling

| Scenario | Strategy |
|----------|----------|
| DB connection failure | Celery auto-retry with backoff |
| LLM API timeout | Retry 3x, then skip posting for this cycle |
| Bluesky API error | Log warning, skip posting |
| Invalid readings data | Log and continue processing remaining data |
| Processor exception | Catch, log to Seq, update `last_run_at` anyway to prevent stuck state |

## 8. Testing Strategy

| Test Type | Scope | Approach |
|-----------|-------|----------|
| Unit | `BaseProcessor`, detection logic | Mock readings, verify trend detection accuracy |
| Unit | `JokeGenerator` | Mock OpenAI client, verify prompt construction |
| Unit | `BlueskyClient` | Mock atproto, verify cooldown enforcement |
| Integration | Full processor flow | Use `model_bakery` for realistic test data |
| Integration | Celery task execution | Use `pytest-celery` with eager mode |
