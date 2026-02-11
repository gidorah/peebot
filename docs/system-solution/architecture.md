# PeeBot Architecture Specification

**Last Updated**: 2026-01-18

---

## 1. Overview

This document outlines the architecture for the ISS Telemetry system as a **Django Modular Monolith**. The system ingests real-time telemetry from ISS Lightstreamer, validates and persists data to TimescaleDB, and runs periodic analytics modules (starting with Pee-Bot) that independently poll the database for event detection.

### 1.1 Key Architectural Principles

1.  **Modularity**: Each Django app represents a bounded context with clear responsibilities.
2.  **Single Source of Truth**: TimescaleDB stores all telemetry data and analytics results.
3.  **Polling Architecture**: Analytics modules poll database periodically using Celery Beat. No complex event streaming (Kafka) is used.
4.  **Independence**: Each analytics module operates independently with its own schedule.
5.  **Async Support**: Leverage Django's ASGI for real-time ingestion and async I/O.
6.  **Single Deployment Unit**: One codebase, one deployment, simpler operations on a single VPS.

---

## 2. System Requirements

| Metric | Target | Notes |
| :--- | :--- | :--- |
| **Throughput** | 70 msg/sec nominal | Tested for 10K msg/sec bursts |
| **Persistence Latency** | P99 < 5s | Ingestion to database |
| **Dashboard Latency** | P99 < 1s | Real-time updates |
| **Analytics Detection** | < 2 minutes | Polling every 30s |
| **Retention** | 30 days | Compression after 7 days |
| **Consistency** | No duplicates | Strict ordering per channel |
| **Deployment** | Single VPS | Via Coolify |

---

## 3. Concrete Tech Stack

All versions are **MANDATORY**. Do not upgrade without RFC.

| Scope | Technology | Version | Rationale |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python | `3.14+` | Latest stable CPython with GIL improvements. |
| **Framework** | Django | `5.2+` | LTS release. |
| **API** | Django REST Framework | `3.15+` | Standard validation/serialization layer. |
| **Async** | Django Channels (Daphne) | `4.0+` | WebSocket support for dashboard. |
| **Database** | PostgreSQL + TimescaleDB | `16` / `2.13` | Time-series optimization. |
| **Ingestion** | lightstreamer-client-lib | `2.2.2` | Official SDK (Sync/Threaded). |
| **Queue** | Celery + Redis | `5.3+` / `7.2` | Polling and background tasks. |
| **AI Client** | openai (Python SDK) | `1.x` | Generic client compatible with OpenRouter. |
| **AI Provider**| DeepSeek V3 | `Latest` | Via OpenRouter. |
| **Social** | atproto | `0.0.65+` | Bluesky AT Protocol SDK. |
| **Validation** | Pydantic | `2.x` | High-performance data validation for ingestion. |
| **Logging** | Structlog + Seq | `24.x` | Structured logging with centralized ingestion. |
| **Pkg Manager** | uv | `Latest` | Fast resolution and locking. |

---

## 4. High-Level Architecture

```
                    ISS Lightstreamer Feed
                 (Real-time ISS Telemetry)
                            |
                            | Event updates
                            v
        +------------------------------------------+
        |   Django Modular Monolith Application    |
        |        (Single Deployment Unit)          |
        +------------------------------------------+
        |                                          |
        |  [Ingestion] -> [Storage] <- [Event]     |
        |     Module         Module    Processors  |
        |                                          |
        |         [Core Module - Utilities]        |
        |                                          |
        |       [Dashboards - Web Interface]       |
        |                                          |
        +------------------------------------------+
                    |              |
                    |              |
                    v              v
            [TimescaleDB]      [Redis] <---- [Flower]
           (Single Source)  (Celery Queue)  (Monitoring)
              of Truth
```

### 4.1 Data Flow Philosophy

**Single Source of Truth**: All telemetry data and analytics results are stored exclusively in TimescaleDB. Redis is used only as an ephemeral job queue for Celery tasks and WebSocket layering. There is no duplicate storage, no event streaming persistence (no Kafka), and no separate databases for different data ages.

---

## 5. Project Structure

```text
peebot/
├── manage.py
├── Justfile                         # Task runner
├── config/                          # Project configuration
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py                      # ASGI for async/WebSocket support
│   ├── wsgi.py
│   └── celery.py                    # Celery configuration
├── apps/
│   ├── core/                        # Shared utilities
│   │   ├── models.py                # Base models, mixins
│   │   ├── serializers.py           # DRF base serializers
│   │   ├── signals.py               # Signal definitions
│   │   └── utils.py
│   ├── telemetry_ingestion/         # Module: Data Ingestion (No models)
│   │   ├── services/
│   │   │   ├── lightstreamer_client.py
│   │   │   ├── validator.py
│   │   │   └── enricher.py          # Domain Normalization (Timestamp Logic)
│   │   └── management/commands/
│   │       └── run_lightstreamer.py
│   ├── telemetry_storage/           # Module: Data Persistence (Owner)
│   │   ├── models.py                # TelemetryReading, TelemetryChannel
│   │   ├── repositories.py          # Data access layer
│   │   └── managers.py              # Custom QuerySet managers
│   ├── event_processors/            # Module: Analytics & Detection
│   │   ├── models.py                # DetectedEvent, ProcessorState
│   │   ├── processors/
│   │   │   └── pee_bot.py           # Urination detector logic
│   │   ├── services/
│   │   │   ├── bluesky_client.py
│   │   │   └── joke_generator.py
│   │   └── tasks.py                 # Celery periodic tasks
│   └── dashboards/                  # Module: Web Interface
│       ├── views.py                 # Dashboard views
│       ├── consumers.py             # WebSocket consumers
│       └── templates/               # HTMX-powered templates
├── static/
├── templates/                       # Base templates
├── tests/                           # Project-wide integration tests
└── docker/                          # Infrastructure (PgBouncer, Redis, DB)
```

---

## 6. Module Breakdown & Dependencies

### 6.1 Model Ownership Principle

Each database model is owned by exactly one module:
-   **telemetry_storage** owns: `TelemetryReading`, `TelemetryChannel`
-   **event_processors** owns: `DetectedEvent`, `ProcessorState`
-   **core** owns: Abstract base models

### 6.2 Module Dependency Flow

```
    core (base models)
        ^
        | imports from
        |
    telemetry_storage
    (owns: TelemetryReading, TelemetryChannel)
        ^                           ^
        |                           |
        | imports models            | queries database (via Repository)
        |                           |
    telemetry_ingestion        event_processors
    (no models)                (owns: DetectedEvent, ProcessorState)
                                    ^
                                    |
                                    | queries database
                                    |
                                dashboards
                            (no model ownership)
```

---

## 7. Communication Patterns

### 7.1 Polling Pattern (Primary)
This is the primary method for inter-module data flow, specifically used for analytics and event detection.

- **Flow**: Celery Beat triggers a task → Task checks `ProcessorState` → Task queries `TelemetryReading` for new data → Task updates `ProcessorState`.
- **Rationale**: Supports complex sliding-window analysis, provides independent schedules per module, and enables easy historical replay.

### 7.2 Django Signals (Intra-Process)
Used sparingly for immediate, non-persistent notifications within a single process.

- **Use Cases**: Notifying the `dashboards` module to broadcast a high-priority event via WebSockets, or triggering local cache invalidation.
- **Constraint**: Signals must **not** be used for cross-module business logic or heavy processing (e.g., analytics).

### 7.3 Internal REST APIs
Used primarily for the `dashboards` module to retrieve historical or current state from other modules.

- **Use Cases**: Dashboard fetching recent readings, listing detected events, or the `telemetry_ingestion` manual injection endpoint used for development/testing.

---

## 8. Component Specifications

### 8.1 Core Module (`apps/core`)

**Purpose**: Shared foundations, base models, and project-wide utilities.

**Key Components**:
1.  **Base Models**:
    - `TimeStampedModel`: Provides `created_at` and `updated_at`.
    - `UUID7Model`: Provides `id = UUIDField` (defaulting to UUIDv7).
    - `SoftDeleteModel`: Provides `deleted_at` and custom manager.
2.  **Telemetry Serializers**:
    -   **API**: DRF serializers for REST endpoints (e.g., Dashboards).
    -   **Ingestion**: Pydantic models for high-performance stream validation (10k/sec).
    -   Handles type coercion (Strings to Decimals).
3.  **Utilities**:
    - Timestamp normalization (UTC conversion).
    - Event ID generation (UUIDv7 based on data timestamp).

### 8.2 Telemetry Storage (`apps/telemetry_storage`)

**Purpose**: Data persistence layer with TimescaleDB optimization.

**Model: `TelemetryChannel`**

Contains metadata for the ~400 ISS telemetry channels monitored by the system.

| Field | Type | Description |
| :--- | :--- | :--- |
| `public_pui` | String | Public Program Unique Identifier (e.g., "NODE3000004"). Unique. |
| `description` | String | Human-readable description of the sensor. |
| `ops_nom` | String | Operations Nomenclature. |
| `eng_nom` | String | Engineering Nomenclature. |
| `unit` | String | Measurement unit (e.g., "percent", "kg"). |
| `created_at` | DateTime | Timestamp of record creation (from `TimeStampedModel`). |
| `deleted_at` | DateTime | Timestamp of soft deletion (from `SoftDeleteModel`). |

**Model: `TelemetryReading` (Hypertable)**

The single source of truth for all ISS telemetry data, optimized as a TimescaleDB hypertable.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | UUIDv7 | Primary key, time-sortable (from `UUID7Model`). |
| `channel` | ForeignKey | Reference to the `TelemetryChannel`. |
| `timestamp` | DateTime | The actual time the measurement was taken. |
| `value` | Decimal | The raw numeric value from the feed. |
| `calibrated_data` | Decimal | Optional calibrated value. |
| `status_class` | String | Metadata describing the data status. |
| `status_indicator`| String | Metadata describing the indicator state. |
| `status_color` | String | Visual status color from the feed. |
| `metadata` | JSON | Extensible field for additional telemetry metadata. |
| `created_at` | DateTime | System-level insertion timestamp (from `TimeStampedModel`). |
| `updated_at` | DateTime | System-level update timestamp (from `TimeStampedModel`). |

**Indexes & Constraints**:
- **Unique Constraint**: Composite key of `(id, timestamp)` for hypertable partitioning integrity.
- **Query Index**: Optimized for `(channel, -timestamp)` for trend analysis.
- **Audit Index**: `(created_at, timestamp)` for ingestion performance monitoring.

**Retention Policy**:
-   **Compression**: 7 days.
-   **Retention**: 30 days.

### 8.3 Telemetry Ingestion (`apps/telemetry_ingestion`)

**Purpose**: Connect to ISS Lightstreamer, validate, enrich, and persist telemetry data.

**Data Flow**:

```text
[ISS Lightstreamer Feed]
          | (Subscription)
          v
[LightstreamerClient] (Threaded SDK)
          | (Callback: loop.call_soon_threadsafe)
          v
[asyncio.Queue] (Raw Dicts)
          | (Consume Loop)
          v
[Validation Service] (Pydantic / Direct)
          | (Valid TelemetryReading objects)
          v
[Ingestion Buffer] (Memory List)
          | (Flush Trigger: >2000 items OR >500ms)
          v
[Repository Layer] (abulk_create)
          |
          v
[TimescaleDB] (TelemetryReading Table)
```

**Pattern**: Sync-to-Async Bridge with Smart Buffering ("Bucket Brigade").
The Lightstreamer SDK is blocking/threaded. We must run it in a management command and bridge to Django's async ORM via a thread-safe Queue.

**Implementation**:
1.  **Command**: `python manage.py run_lightstreamer`
    *   *Resilience*: Exponential backoff (1s to 60s) for connection drops.
    *   *Shutdown*: Must catch SIGINT/SIGTERM to flush remaining buffer items before exit.
2.  **Producer**: `LightstreamerClient` pushes raw dicts to `asyncio.Queue` (non-blocking).
    *   **Backpressure**: Queue MUST be bounded (e.g., `maxsize=50000`, approx 5s burst capacity).
    *   **Overflow Strategy**: Drop **oldest** items when full to preserve latest telemetry and prevent OOM.
3.  **Consumer**: Async worker loop pulls from Queue, validates using Pydantic, and passes to **Enrichment Service**.
4.  **Enrichment**: `Enricher.normalize()` handles complex domain logic:
    *   Converts ISS "Hours since start of year" to standard UTC `datetime`.
    *   Handles Year Rollover edge cases (e.g., processing Dec 31st data on Jan 1st).
    *   *Note*: System metadata like `id` (UUIDv7) and `created_at` are handled by Model defaults, not this service.
5.  **Write Strategy**: Validated & enriched items are appended to `IngestionBuffer` and flushed to DB using `TelemetryReading.objects.abulk_create()`.
    *   *Latency Goal*: P99 persistence < 5s.

### 8.4 Event Processors (`apps/event_processors`)

**Purpose**: Independent analytics modules that poll TimescaleDB for pattern detection and event generation.

**Architectural Rationale: Why Polling?**

The system deliberately avoids complex event streaming infrastructure (e.g., Kafka, RabbitMQ) in favor of a polling architecture for the following reasons:

1.  **Sliding Window Analysis**: Analytics modules (like PeeBot) must analyze trends over time (e.g., "is the tank level increasing over the last 10 minutes?"). Querying a time-series database for a window of data is natively supported and efficient, whereas streaming windowing requires complex state management.
2.  **Independence & Isolation**: Each analytics module operates on its own schedule (e.g., 30s vs. 5m) and maintains its own processing state. Failure in one processor does not block others or the ingestion pipeline.
3.  **Historical Replay & Backfilling**: By adjusting the `last_processed_timestamp` timestamp in `ProcessorState`, any module can re-process historical data. This is invaluable for testing new algorithms or recovering from downtime.
4.  **Operational Simplicity**: A single database as the "Single Source of Truth" significantly reduces infrastructure overhead, monitoring complexity, and the potential for data drift between a stream and a store.
5.  **Future Scalability**: New analytics modules can be added simply by creating a new Celery task and a `ProcessorState` record, with zero changes required to the ingestion pipeline.

**Model: `DetectedEvent`**

Stores results of analytics processing, such as detected urination events or temperature spikes.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | UUIDv7 | Primary key, time-sortable (from `UUID7Model`). |
| `event_type` | String | Type of event (e.g., 'urination', 'temp_spike'). |
| `channel_id` | String | The PUI of the channel where the event was detected. |
| `detected_at` | DateTime | The logical timestamp of the event occurrence. |
| `confidence` | Decimal | Detection confidence score (0.0 to 1.0). |
| `metadata` | JSON | Detection details (e.g., trend data points). |
| `posted_at` | DateTime | Timestamp when the event was shared to social media. |
| `tweet_id` | String | ID of the resulting tweet. |
| `created_at` | DateTime | Timestamp of record creation (from `TimeStampedModel`). |

**Model: `ProcessorState`**

Maintains the state for each analytics processor to support resumption and historical replay.

| Field | Type | Description |
| :--- | :--- | :--- |
| `processor_name` | String | Unique name of the processor (e.g., 'PeeBot'). |
| `last_processed_timestamp`| DateTime | Timestamp of the last data point successfully analyzed. |
| `last_run_at` | DateTime | Timestamp of the last time the processor execution started. |
| `state_data` | JSON | Processor-specific state (e.g., sliding window buffers). |
| `updated_at` | DateTime | Last time the state was updated (from `TimeStampedModel`). |

**Architecture**: Polling Pattern with Jitter.

```
[Celery Beat] --(30s)--> [PeeBot Task] --(Random Jitter 0-5s)--> [Query TimescaleDB]
                                |
                           (Detection)
                                |
                                v
                           [DetectedEvent]
                                +
                         [Bluesky Client] <--(Check Cooldown)-- [ProcessorState]
```

**Implementation Note**:
-   **Jitter**: All processor tasks MUST implement a random sleep (0-5s) at startup. This prevents "Thundering Herd" CPU spikes on the database when multiple processors share the same schedule alignment.

**PeeBot Specifics**:
-   **Schedule**: Every 30 seconds.
-   **Target**: NODE3000004 (UPA Tank Level).
-   **Logic**: Detect increasing trend over 5-10 minutes.
-   **Cooldown**: **30 Minutes** between tweets (Incoming Doc standard).
-   **AI**: DeepSeek V3 (via OpenRouter) for "Dry, scientific, slightly absurd" humor.

### 8.5 Dashboards (`apps/dashboards`)

**Purpose**: Real-time web interface for visualizing telemetry data and detected events.

**Real-Time Update Strategy**:
The dashboard employs a hybrid approach to balance real-time responsiveness with server scalability.

1.  **Initial Load**: standard HTTP request fetches the recent history and current state from TimescaleDB.
2.  **Standard Updates (HTMX Polling)**: The UI polls the server every 2-3 seconds via HTMX for standard telemetry updates. These responses are lightweight HTML fragments cached in Redis (5s TTL) to minimize database load.
3.  **High-Priority Events (WebSockets)**: Only critical events (e.g., detected urination, system alerts) are pushed instantly via WebSockets using Django Channels.
4.  **Visualizations**: Historical trends and sliding window analyses are rendered client-side using Chart.js, fed by historical data points from the internal REST API.

**Architecture Flow**:

```text
[Web Browser]
      |
      +---(HTTP GET)---> [Gunicorn] ---> [Django Views] ---> [TimescaleDB]
      |                    (Initial Page Load & Historical Data)
      |
      +---(HTMX Poll)---> [Gunicorn] ---> [Redis Cache]
      |                    (2-3s Telemetry Fragments)
      |
      +---(WebSockets)---> [Daphne] <--- [Redis Layer] <--- [Django Signals]
                           (Instant Event Notifications)
```

**Key Features**:
- **Channel Browser**: Searchable interface for all monitored ISS telemetry channels.
- **Live Widgets**: Real-time status indicators for "high-priority" channels.
- **Event Timeline**: Interactive list of `DetectedEvent` records with drill-down capabilities.
- **Trend Charts**: Dynamic time-series visualization for any selected channel.

---

## 9. Infrastructure & Ops

### 9.1 Database Connection Pooling (PgBouncer)

**Deployment**: Single VPS via Coolify.
**Service**: PgBouncer in **Session Mode**.

**Configuration**:
-   **Django**: `CONN_MAX_AGE = 0` (Forces connection return to pool).
-   **Pool Size**:
    -   Dev: 10 connections.
    -   Prod: 25 connections.

**Timeout Rationale**:
| Parameter | Value | Purpose |
| :--- | :--- | :--- |
| `server_idle_timeout` | 300s | Reclaims backend connections after 5 minutes of inactivity. |
| `query_timeout` | 60s | Kills runaway queries to prevent resource exhaustion. |
| `idle_transaction_timeout` | 60s | Kills forgotten transactions to prevent lock buildup. |
| `server_reset_query` | `DISCARD ALL` | Cleans connection state (temp tables, locks) before reuse. |

**Authentication Model (Hybrid SCRAM)**:
1. **Auth User**: A single user (`pgbouncer_auth`) is stored in `userlist.txt` as a SCRAM-SHA-256 hash.
2. **Dynamic Verification**: PgBouncer uses `auth_query = SELECT usename, passwd FROM pg_shadow WHERE usename=$1` to verify application users directly against the database.
3. **Secret Management**: `userlist.txt` is injected via `PGBOUNCER_USERLIST_B64` env var in the production entrypoint.

### 9.2 Process Management & Monitoring

**Process Model (Systemd)**:
All long-running components are managed as independent systemd services with `Restart=always` and exponential backoff.
- **`peebot-web`**: Gunicorn (WSGI) for standard HTTP traffic.
- **`peebot-asgi`**: Daphne (ASGI) for WebSocket and async traffic.
- **`peebot-ingestion`**: The `run_lightstreamer` management command.
- **`peebot-worker`**: Celery worker for analytics tasks.
- **`peebot-beat`**: Celery Beat for task scheduling.

**Observability**:
- **Logging**: Structured JSON logs (Structlog) aggregated in **Seq** (Dev/Staging) or centralized log store.
- **Tracing**: Logs tagged with `request_id`, `Application`, and `Environment` for distributed tracing.
- **Metrics**: Prometheus + Grafana for monitoring DB performance and ingestion throughput.
- **Errors**: Sentry integration for real-time application error tracking.

### 9.3 Deployment Structure

```
[Nginx] -> [Gunicorn (WSGI)] + [Daphne (ASGI)]
                  |                   |
             [PgBouncer]         [Redis]
                  |
            [TimescaleDB]
```

---

## 10. Performance & Scaling Strategy

### 10.1 Handling High Throughput (10k msg/sec)
1.  **Batch Inserts**: The `telemetry_ingestion` module must use `abulk_create` to flush readings in batches (e.g., every 500ms or 2,000 items). This minimizes database round-trips and transaction overhead.
2.  **Fast Validation**: Use Pydantic or direct dict manipulation instead of DRF serializers in the hot path to minimize CPU overhead per message.
3.  **Async I/O**: Leveraging Django's ASGI and `asyncio` for the ingestion pipeline ensures that blocking network I/O from the Lightstreamer feed does not starve the application of resources.
4.  **Connection Pooling**: Using PgBouncer in session mode is mandatory to handle the high volume of short-lived queries from multiple workers without exhausting PostgreSQL's connection limit.

### 10.2 Caching Strategy
- **Dashboard Cache**: Recent readings for the dashboard overview should be cached in Redis with a short TTL (e.g., 2-5s) to prevent redundant heavy queries on the `TelemetryReading` table.
- **Continuous Aggregates**: Use TimescaleDB continuous aggregates for historical charts (hourly/daily rollups) to avoid scanning millions of raw rows for simple trend visualizations.

### 10.3 Horizontal Scaling (Process Model)
- **Web Scaling**: Increase Gunicorn (WSGI) workers for standard HTTP load and Daphne (ASGI) workers for WebSocket concurrency.
- **Worker Scaling**: Celery workers can be scaled horizontally by increasing concurrency or adding nodes to handle more frequent analytics polling.
- **Ingestion**: The `run_lightstreamer` command is a singleton process; however, multiple instances can be run if partitioned by telemetry channel groups in the future.

---

## 11. Testing Strategy

### 11.1 Test Hierarchy
The project follows a three-tiered testing approach to ensure reliability from individual components to full system performance.

| Tier | Location | Scope | Tools |
| :--- | :--- | :--- | :--- |
| **Unit Tests** | `apps/<module>/tests/` | Individual services and logic in isolation. | `pytest`, `pytest-mock` |
| **Integration Tests** | `tests/` | Interaction between modules (e.g., Ingestion to DB). | `pytest-django`, `model_bakery` |
| **System Tests** | `tests/` | End-to-end flows, performance, and resilience. | `locust` or `k6`, `Docker Compose` |

### 11.2 Key Test Scenarios
1.  **Ingestion Pipeline**: Validate that the `UpdateListener` correctly maps raw keys and that the `IngestionBuffer` flushes data reliably without loss.
2.  **Analytics Logic**: Test the `PeeBotProcessor` against mock sliding-window datasets (e.g., simulating a 10-minute urine tank level rise).
3.  **Concurrency & Load**: Simulate 10,000 messages/second to verify that PgBouncer, the Ingestion Buffer, and TimescaleDB hypertables handle the load within SLA.
4.  **Resilience**: Simulate Lightstreamer connection drops to verify exponential backoff and reconnection logic.
5.  **Retention & Compression**: Verify that TimescaleDB policies correctly compress chunks after 7 days and drop them after 30 days.

### 11.3 Test Database
A dedicated TimescaleDB instance must be used for testing, with migrations configured to automatically create hypertables for the `TelemetryReading` model.
