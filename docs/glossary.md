# PeeBot Glossary

A reference glossary for the PeeBot ISS Telemetry Data Analytics System. Covers domain-specific terminology from ISS telemetry, system architecture, detection algorithms, and infrastructure components.

---

## ISS Telemetry

### Lightstreamer
A real-time data streaming protocol and client library used to subscribe to live ISS telemetry feeds. PeeBot uses the official `lightstreamer-client-lib` (v2.2.2) to maintain a persistent connection to the ISS data stream.

### NODE3000005
The Public PUI (Program Unique Identifier) for the UPA (Urine Processor Assembly) tank level sensor on the ISS. This is the primary telemetry channel monitored by PeeBot for fill event detection.

### Public PUI (Public Program Unique Identifier)
A unique alphanumeric identifier (e.g., `NODE3000005`) assigned to each ISS telemetry channel. Used as the canonical channel identifier throughout PeeBot's data models and configuration.

### TelemetryChannel
A database model that stores metadata for an ISS telemetry channel. Each channel has a `public_pui`, `description`, `ops_nom` (operations nomenclature), `eng_nom` (engineering nomenclature), and `unit`. Approximately 400 channels are tracked.

### TelemetryReading
The primary data model (TimescaleDB hypertable) that stores individual telemetry measurements. Each reading records a `channel`, `timestamp`, `value`, and optional status/metadata fields. Uniqueness is enforced by the composite key `(channel, timestamp)`.

### UPA (Urine Processor Assembly)
The ISS system that processes astronaut urine into potable water. PeeBot monitors the UPA tank level sensor (`NODE3000005`) to detect fill events (indicating active processing).

---

## Architecture

### Bounded Context
A DDD (Domain-Driven Design) concept applied to PeeBot's modular architecture. Each Django app represents a bounded context with clear ownership of its models and responsibilities. Modules must not import models from other modules except via defined ownership rules.

### Django Modular Monolith
PeeBot's architectural pattern: a single deployable Django application divided into self-contained modules (`core`, `telemetry_storage`, `telemetry_ingestion`, `event_processors`, `dashboards`). Provides the simplicity of a monolith with the organizational benefits of modules.

### Ingestion Buffer
An in-memory list used by `telemetry_ingestion` to batch telemetry readings before flushing to TimescaleDB. Flushes when it reaches 2,000 items or every 500ms, whichever comes first.

### Repository Pattern
A data access abstraction layer used in `telemetry_storage`. Repository functions (e.g., `abulk_create`) wrap ORM queries, making the data layer testable and decoupled from business logic.

### Single Source of Truth
An architectural principle in PeeBot: TimescaleDB is the only persistent store for telemetry data and analytics results. No intermediate streaming queues (e.g., Kafka) or duplicate stores are used.

### Sync-to-Async Bridge
The ingestion pattern that bridges the synchronous Lightstreamer SDK (threaded) with Django's async ORM. Uses a thread-safe `asyncio.Queue` to pass raw data from the sync Lightstreamer callback to an async consumer task.

---

## Data Models

### DetectedEvent
A model in `event_processors` that records a confirmed detection event (e.g., a UPA fill). Fields include `event_type`, `channel_id`, `detected_at`, `confidence`, and `metadata`. Linked to `SocialPost` records for outbound social media activity.

### ProcessorState
A model in `event_processors` that stores per-processor state to support resumption and historical replay. Key fields: `processor_name`, `last_processed_timestamp`, and `state_data` (JSON for processor-specific state like sliding window buffers).

### SocialPost
A model in `event_processors` that tracks social media posts generated from `DetectedEvent` records. Supports multi-platform posting with status tracking (`PENDING`, `SUCCESS`, `FAILED`).

### UUID7Model
An abstract base model in `core` that provides a time-sortable UUIDv7 primary key (`id`). Used by all major PeeBot models to enable time-ordered queries by ID.

---

## Detection Algorithm

### Confidence Score
A decimal value (0.0 to 1.0) calculated by the `PeeBotProcessor` representing the certainty of a detected fill event. Based on the magnitude and consistency of the tank level increase.

### Fill Event
A PeeBot-specific detected event representing active UPA tank level increase (astronaut urination). Confirmed using a two-phase detection: (1) ≥2% net increase over any 30-second window within a 10-minute observation, then (2) level remains stable (≤1% fluctuation) over a 60-second stability window.

### Net-Change-Over-Window Algorithm
PeeBot's primary detection algorithm. Computes the net change in tank level between the oldest and newest reading within a sliding time window. A fill event requires a ≥2% net delta threshold over a 30-second sub-window.

### Observation Window
The 10-minute time window queried by the `PeeBotProcessor` when searching for fill events. Each Celery task invocation queries the last 10 minutes of `TelemetryReading` data for `NODE3000005`.

### Sliding Window
A time-based data analysis technique where a fixed-duration window moves forward in time. PeeBot uses a 30-second sliding window within the larger 10-minute observation window to detect net tank level changes.

### Stability Window
A 60-second post-detection window used to confirm a fill event. After the initial ≥2% delta is detected, the tank level must remain within ±1% tolerance for 60 seconds before the event is officially confirmed.

---

## Infrastructure

### Celery Beat
The Celery scheduler component that triggers periodic PeeBot tasks. Configured to invoke the `PeeBotProcessor` task every 30 seconds.

### HTMX Polling
A lightweight technique used in the PeeBot dashboard where the browser polls the server every 2–3 seconds for telemetry updates using HTML-over-the-wire (HTMX). Reduces WebSocket load for non-priority channel updates.

### Hypertable
A TimescaleDB concept: a PostgreSQL table automatically partitioned by time. `TelemetryReading` is configured as a hypertable with 1-day chunks, enabling efficient time-series queries and automatic compression/retention policies.

### PgBouncer
A PostgreSQL connection pooler deployed in session mode between Django and TimescaleDB. Manages up to 25 production connections to prevent exhausting PostgreSQL's connection limit under high throughput.

### Retention Policy
A TimescaleDB policy applied to the `TelemetryReading` hypertable. Chunks older than 7 days are compressed; chunks older than 30 days are automatically dropped.

### TimescaleDB
A PostgreSQL extension that provides time-series optimizations: hypertables (time-partitioned tables), automatic compression, retention policies, and continuous aggregates. PeeBot uses TimescaleDB as its primary data store.

---

## Services & Integrations

### AT Protocol (atproto)
The decentralized social networking protocol underlying Bluesky. PeeBot uses the `atproto` Python SDK to post detected fill events to the Bluesky social network.

### BlueskyClient
A service class in `apps/event_processors/services/bluesky_client.py` that wraps the `atproto` SDK. Handles session management, post creation, and enforces a 30-minute cooldown period between posts to avoid rate limit violations.

### Cooldown Period
The minimum time (default: 30 minutes) that must elapse between consecutive Bluesky posts from PeeBot. Enforced by `BlueskyClient` using `ProcessorState` to track the last post timestamp.

### JokeGenerator
A service class in `apps/event_processors/services/joke_generator.py` that calls the OpenRouter API (DeepSeek V3 model) to generate contextual humorous content for fill event social media posts. Style: "dry, scientific, slightly absurd".

### OpenRouter
An API gateway service used by `JokeGenerator` to access the DeepSeek V3 language model. Provides a unified API compatible with the OpenAI Python SDK.

### Seq
A structured log aggregation server used in development. PeeBot sends structured JSON logs (via `structlog`) to Seq for centralized viewing. Not used in production (stdout-only logging).
