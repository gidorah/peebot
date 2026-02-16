
## Django Modular Monolith Architecture

---

## Overview

This document outlines the architecture for the ISS Telemetry system as a **Django modular monolith**. The system ingests real-time telemetry from ISS Lightstreamer, validates and persists data to TimescaleDB, and runs periodic analytics modules (starting with Pee-Bot) that independently poll the database for event detection.

### Key Architectural Principles

1. **Modularity**: Each Django app represents a bounded context with clear responsibilities
2. **Single Source of Truth**: TimescaleDB stores all telemetry data and analytics results
3. **Polling Architecture**: Analytics modules poll database periodically using Celery Beat
4. **Independence**: Each analytics module operates independently with its own schedule
5. **Async Support**: Leverage Django's ASGI for real-time ingestion and async I/O
6. **Single Deployment Unit**: One codebase, one deployment, simpler operations

---

## System Requirements

- **Throughput**: 70 msg/sec nominal, tested for 10K msg/sec
- **Latency**: P99 < 1s for dashboards, < 5s for persistence, < 2 minutes for analytics detection
- **Retention**: 30 days (automatic compression after 7 days reduces storage)
- **Consistency**: No duplicates, strict ordering per telemetry channel
- **Deployment**: Single VPS with Coolify
- **Real-time**: Dashboard updates < 1s, Analytics detection within minutes

---

## High-Level Architecture

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
                    v              v
            [TimescaleDB]      [Redis]
           (Single Source)  (Celery Queue)
              of TruthLong-runn
```

### Data Flow Philosophy

**Single Source of Truth**: All telemetry data and analytics results are stored exclusively in TimescaleDB. Redis is used only as an ephemeral job queue for Celery tasks. There is no duplicate storage, no event streaming persistence (no Kafka), and no separate databases for different data ages.

---

## Django Modular Monolith Structure

```
iss_telemetry_project/
|-- manage.py
|-- config/                          # Project configuration
|   |-- __init__.py
|   |-- settings/
|   |   |-- base.py
|   |   |-- development.py
|   |   +-- production.py
|   |-- urls.py
|   |-- asgi.py                     # ASGI for async/WebSocket support
|   |-- wsgi.py
|   +-- celery.py                   # Celery configuration
|
|-- apps/
|   |-- core/                       # Shared utilities
|   |   |-- models.py               # Base models, mixins
|   |   |-- serializers.py          # DRF serializers
|   |   |-- signals.py              # Signal definitions
|   |   |-- exceptions.py
|   |   +-- utils.py
|   |
|   |-- telemetry_ingestion/       # Module 1: Data Ingestion
|   |   |-- __init__.py
|   |   |-- services/
|   |   |   |-- lightstreamer_client.py
|   |   |   |-- validator.py
|   |   |   +-- enricher.py
|   |   |-- views.py               # Manual injection endpoint
|   |   +-- management/
|   |       +-- commands/
|   |           +-- run_lightstreamer.py
|   |
|   |-- telemetry_storage/         # Module 2: Data Persistence
|   |   |-- models.py              # TelemetryReading, TelemetryChannel
|   |   |-- serializers.py         # DRF model serializers
|   |   |-- repositories.py        # Data access layer
|   |   |-- managers.py            # Custom QuerySet managers
|   |   +-- migrations/
|   |
|   |-- event_processors/          # Module 3: Analytics & Detection
|   |   |-- models.py              # DetectedEvent, ProcessorState
|   |   |-- processors/
|   |   |   |-- base.py
|   |   |   +-- pee_bot.py        # Urination detector
|   |   |-- services/
|   |   |   |-- twitter_client.py
|   |   |   +-- joke_generator.py
|   |   |-- tasks.py              # Celery periodic tasks
|   |   +-- management/
|   |       +-- commands/
|   |           +-- run_pee_bot.py
|   |
|   +-- dashboards/                # Module 4: Web Interface
|       |-- models.py
|       |-- views.py               # Dashboard views
|       |-- consumers.py           # WebSocket consumers
|       |-- urls.py
|       +-- templates/
|           +-- dashboards/
|
|-- static/
|-- templates/
|-- tests/                         # Project-wide tests
|-- requirements/
|   |-- base.txt
|   |-- development.txt
|   +-- production.txt
+-- docker-compose.yml
```

---

## Module Dependencies and Model Ownership

In a modular monolith, modules can import from each other when there's a clear dependency relationship. This is different from microservices where each service must be completely independent.

### Model Ownership Pattern

**Single Owner Principle**: Each database model is owned by exactly one module:

- **telemetry_storage** owns: `TelemetryReading`, `TelemetryChannel`
- **event_processors** owns: `DetectedEvent`, `ProcessorState`
- **core** owns: Abstract base models (not actual tables)

### Import Relationships

```
Module Dependency Flow:

    core (base models)
        ^
        | imports from
        |
    telemetry_storage
    (owns: TelemetryReading, TelemetryChannel)
        ^                           ^
        |                           |
        | imports models            | queries database
        |                           | (no Python imports)
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

**Key Points**:
- Arrows point FROM dependent module TO the module it depends on
- `telemetry_storage` is the foundation - other modules depend on it
- `event_processors` queries telemetry data but doesn't import storage code
- `dashboards` queries everything but owns nothing

### Model Ownership Diagram

```
+------------------------------------------+
|         TimescaleDB Tables               |
+------------------------------------------+
| TelemetryReading    | Owner: storage    |
| TelemetryChannel    | Owner: storage    |
| DetectedEvent       | Owner: processors |
| ProcessorState      | Owner: processors |
+------------------------------------------+Long-runn

Module Access Pattern:
- storage: Defines and owns telemetry models
- ingestion: Imports from storage, writes to DB
- processors: Defines analytics models, reads telemetry via queries
- dashboards: Reads all models via queries
```

**Key Rules**:
1. **Database models live in one place** - No duplicate model definitions across modules
2. **Modules can import models** - Ingestion module imports TelemetryReading and TelemetryChannel from storage module
3. **Analytics modules query database** - Event processors import models from storage to query telemetry data
4. **Use repository pattern** - Abstract database access layer for easier testing and reduced coupling

This approach provides modularity while avoiding the overhead of inter-service communication in microservices.

---

## Module Breakdown

### 1. Core Module (`apps/core/`)

**Purpose**: Shared utilities, base models, and common functionality across all modules.

**Components**:
- **Base Models**: Abstract Django models providing common fields (timestamps, UUIDs, soft-delete)
- **Serializers**: Django REST Framework serializers for telemetry validation with field mapping from Lightstreamer format
- **Signals**: Django signal definitions for in-process event notifications (optional)
- **Utilities**: Helper functions for enrichment (event ID generation, timestamp normalization)

**Key Responsibilities**:
- Provide reusable base model classes with automatic timestamp tracking
- Define DRF serializers for validating incoming telemetry data (field validation, type coercion, cross-field checks)
- Generate unique event IDs for all telemetry readings
- Normalize timestamps and handle timezone conversions
- Provide common exception classes

**Technologies**:
- Django ORM for base models
- Django REST Framework for serializers
- Django signals for event propagation (if needed)
- Python dataclasses for data transfer objects

---

### 2. Telemetry Ingestion Module (`apps/telemetry_ingestion/`)

**Purpose**: Connect to ISS Lightstreamer, ingest, validate, enrich, and persist telemetry data.

**Important**: This module does NOT define database models. It imports `TelemetryReading` and `TelemetryChannel` models from the `telemetry_storage` module. This follows the modular monolith principle where models are owned by a single module and imported by others.

**Architecture Flow**:

```
        Lightstreamer Feed (ISS ISSLIVE)
                    |
                    | Updates on data change
                    v
        +-------------------------+
        | Async Lightstreamer     |
        | Client                  |
        | - Maintains connection  |
        | - Subscribes to ~400    |
        | - Handles reconnection  |
        +-------------------------+
                    |
                    v
        +-------------------------+
        | Validation Service      |
        | - DRF Serializers       |
        | - Field validation      |
        | - Type coercion         |
        +-------------------------+
                    |
                    v
        +-------------------------+
        | Enrichment Service      |
        | - Add event_id (UUID)   |
        | - Add ingested_at       |
        | - Normalize fields      |
        +-------------------------+
                    |
                    v
        +-------------------------+
        | Repository Layer        |
        | - Deduplication check   |
        | - Async DB write        |
        | - Error handling        |
        +-------------------------+
                    |
                    v
            [TimescaleDB]
         (Single Source of Truth)
```

**Key Components**:

1. **Lightstreamer Client Service**:
   - Maintains persistent async connection to ISS Lightstreamer
   - Subscribes to configured telemetry items (channels)
   - Handles connection drops and reconnection with exponential backoff
   - Parses incoming update events into structured format

2. **Validation Service**:
   - Uses Django REST Framework serializers for schema validation
   - Maps Lightstreamer field names to internal format
   - Performs field-level validation (timestamp not in future, numeric values)
   - Performs cross-field validation (calibrated_data vs value consistency)
   - Rejects malformed data and logs validation errors

3. **Enrichment Service**:
   - Generates unique event_id (UUID4) for each telemetry reading
   - Adds ingested_at timestamp (server time when received)
   - Normalizes field names and formats
   - Prepares data for persistence

4. **Repository Layer** (from `telemetry_storage` module):
   - Imported and used by ingestion module
   - Abstracts database operations from business logic
   - Checks for duplicates using event_id or timestamp+channel combination
   - Uses async database writes for performance
   - Handles database errors with retry logic
   - Auto-creates TelemetryChannel records for new item_ids

5. **HTTP Injection Endpoint**:
   - REST API endpoint for manual test data injection
   - Uses same validation pipeline as Lightstreamer data
   - Requires authentication via DRF permissions
   - Useful for development and testing

**Technologies**:
- `lightstreamer-client-lib` or custom WebSocket client
- Django REST Framework serializers for validation
- Django async views and ORM operations
- Django management commands for long-running processes
- Imports: `TelemetryReading`, `TelemetryChannel` from `apps.telemetry_storage.models`

---

### 3. Telemetry Storage Module (`apps/telemetry_storage/`)

**Purpose**: Data persistence layer with TimescaleDB optimization and efficient querying.

**Data Models**: (Should review, needs updates)

```
=================================================
           TimescaleDB Schema
=================================================

TelemetryReading (Hypertable)
  - id: BigAutoField (primary key)
  - channel: ForeignKey -> TelemetryChannel
  - timestamp: DateTimeField (indexed)
  - value: DecimalField
  - calibrated_data: DecimalField - ?
  - status_class: CharField - ?
  - status_indicator: CharField - ?
  - status_color: CharField - ?
  - event_id: UUIDField (unique)
  - ingested_at: DateTimeField
  - metadata: JSONField

  Indexes:
    * (channel, timestamp) - Primary query pattern
    * (event_id) - Deduplication
    * (ingested_at) - Processing order

  Optimizations:
    * Automatic time partitioning (1-day chunks)
    * Automatic compression after 7 days
    * Retention: Drop chunks > 30 days

-------------------------------------------------

TelemetryChannel (Regular Table)
  - id: AutoField (primary key)
  - item_id: CharField (unique, e.g., "NODE3000005")
  - description: TextField
  - module_name: CharField
  - unit: CharField
  - is_active: BooleanField
  - created_at: DateTimeField
  - updated_at: DateTimeField

  Contains ~400 ISS telemetry channels

=================================================
```

**Key Features**:

1. **Hypertable Configuration**: TelemetryReading table converted to TimescaleDB hypertable for efficient time-series queries
2. **Automatic Partitioning**: Data automatically partitioned by time (1-day chunks)
3. **Compression**: Older data (>7 days) automatically compressed to save storage
4. **Retention Policies**: Automatic deletion of data older than 30 days
5. **Custom Managers**: Django QuerySet managers for common query patterns (get_recent, get_by_channel, get_sliding_window)
6. **Repository Pattern**: Clean abstraction over database operations for testability

**Technologies**:
- Django ORM with TimescaleDB backend
- Custom Django model managers
- Repository pattern for data access
- PostgreSQL native features (JSONB, time-based indexing)

---

### 4. Event Processors Module (`apps/event_processors/`)

**Purpose**: Independent analytics modules that poll TimescaleDB for pattern detection and event generation.

**Architecture - Polling Pattern**:

```
        +------------------------------------------+
        |  TimescaleDB (Single Source of Truth)   |
        +------------------------------------------+
        | [TelemetryReading] [DetectedEvent]      |
        |           [ProcessorState]              |
        +------------------------------------------+
                    |         |         |
                    |         |         |
              Every 30s   Every 60s  Every 5m
                    |         |         |
                    v         v         v
            +--------+  +--------+  +--------+
            | PeeBot |  |  Temp  |  |  CO2   |
            |  Task  |  |Analyzer|  |Monitor |
            +--------+  +--------+  +--------+
                    |         |         |
                    +-------- | --------+
                              |
                              v
                    +------------------+
                    | External Actions |
                    | (Twitter, Email) |
                    +------------------+

Each processor:
1. Queries ProcessorState for last_processed_timestamp
2. Queries TelemetryReading for new data
3. Analyzes sliding window (e.g., last 10 min)
4. Detects events and stores results
5. Updates ProcessorState timestamp
```

**Why Polling Instead of Signals/Kafka**:

1. **Sliding Window Analysis**: Analytics modules need to analyze trends over time (e.g., "is tank level increasing over last 10 minutes?"). Polling naturally supports this pattern by querying time ranges.

2. **Independence**: Each analytics module operates independently with its own schedule and state. No coupling between ingestion and analytics.

3. **Historical Replay**: Modules can replay historical data by adjusting their last_processed_timestamp timestamp. Perfect for development, testing, and backfilling.

4. **Simplicity**: No event streaming infrastructure (no Kafka). Database is single source of truth.

5. **Future Scalability**: Easy to add new analytics modules without modifying existing code.

**Data Models**:

**DetectedEvent Table:**
- id: AutoField
- event_type: CharField (e.g., 'urination', 'temperature_spike')
- channel_id: CharField
- detected_at: DateTimeField
- confidence: DecimalField (0.0-1.0)
- metadata: JSONField (detection details)
- posted_at: DateTimeField (nullable, when tweeted)
- tweet_id: CharField (nullable)
- created_at: DateTimeField

**ProcessorState Table:**
- id: AutoField
- processor_name: CharField (e.g., 'PeeBot', 'TempAnalyzer')
- last_processed_timestamp: DateTimeField
- last_run_at: DateTimeField
- state_data: JSONField (processor-specific state)
- updated_at: DateTimeField

**Key Components**:

1. **Base Processor Class**: Abstract base class defining the polling pattern interface (get_last_processed, query_new_data, detect_events, update_state)

2. **PeeBot Processor**:
   - Queries `TelemetryReading` from `telemetry_storage` module (via imports or repository)
   - Monitors NODE3000005 (Urine Processor Assembly Tank Level)
   - Detects tank filling pattern (increasing trend over 5-10 minutes)
   - Generates humorous tweets using joke generation service
   - Posts to Twitter with cooldown period (minimum 30 minutes between tweets)
   - Stores detected events in its own `DetectedEvent` table

3. **Future Processors**: Template for adding new analytics modules (temperature analyzer, CO2 monitor, etc.)

4. **Twitter Client Service**: Wrapper around Twitter API for posting tweets with rate limiting and error handling

5. **Joke Generator Service**: Generates contextual humor based on telemetry data

**Note**: This module owns the `DetectedEvent` and `ProcessorState` models (analytics results), but imports/queries the `TelemetryReading` model from `telemetry_storage` (source data).

**Celery Beat Schedule Configuration**:

Each processor has its own periodic task configured in Celery Beat:
- PeeBot: Runs every 30 seconds
- Future Temperature Analyzer: Runs every 60 seconds
- Future CO2 Monitor: Runs every 5 minutes

**Processing Flow for PeeBot**:

1. Celery Beat triggers run_pee_bot_detection task every 30 seconds
2. Task queries ProcessorState to get last_processed_timestamp timestamp
3. Query TelemetryReading for new data since last_processed_timestamp for channel NODE3000005
4. If no new data, skip processing
5. Query sliding window (last 10 minutes) of readings for trend analysis
6. Apply detection algorithm (check for increasing tank level pattern)
7. If urination event detected:
   - Create DetectedEvent record
   - Generate joke using joke generation service
   - Post to Twitter if cooldown period has passed
   - Update tweet_id and posted_at in DetectedEvent
8. Update ProcessorState with current timestamp
9. Task completes

**Technologies**:
- Celery for periodic task scheduling
- Celery Beat for cron-like scheduling
- Redis as Celery broker/result backend (ephemeral only)
- Tweepy for Twitter API integration
- Custom processor classes with strategy pattern

---

### 5. Dashboards Module (`apps/dashboards/`)

**Purpose**: Real-time web interface for visualizing telemetry data and detected events.

**Architecture Flow**:

```
            Web Browser
    +------------------------+
    | HTML/HTMX UI           |
    | (Dashboard)            |
    |                        |
    | WebSocket Connection   |
    | (Real-time updates)    |
    +------------------------+
          |            |
          | HTTP       | WebSocket (ws://)
          v            v
    +------------------------+
    | Django Application     |
    | (ASGI)                 |
    +------------------------+
    | Dashboard Views   |    |
    | (HTTP handlers)   |    |
    |                   |    |
    | WebSocket         |    |
    | Consumers         |    |
    +------------------------+
            |
            | Repository Layer
            v
       [TimescaleDB]
     (Query for data)
```

**Key Features**:

1. **Real-Time Dashboard**: Live telemetry visualization updated via WebSocket
2. **Channel Browser**: Browse and search all ~400 telemetry channels
3. **Time-Series Charts**: Historical data visualization with Chart.js or similar
4. **Event Timeline**: Display detected events (urination events, etc.)
5. **Channel Detail Pages**: Deep dive into specific telemetry channels
6. **Filtering and Search**: Filter by module, status, value ranges

**Components**:

1. **Django Views (HTTP)**:
   - Dashboard homepage with overview
   - Channel list view with pagination
   - Channel detail view with historical charts
   - Event timeline view
   - REST API endpoints for HTMX partial updates

2. **WebSocket Consumers (Django Channels)**:
   - Real-time telemetry broadcast consumer
   - Per-channel subscription consumer
   - Event notification consumer
   - Connection management and authentication

3. **Templates**:
   - Base template with navigation
   - Dashboard template with real-time widgets
   - Channel list template with HTMX integration
   - Channel detail template with interactive charts

**Technologies**:
- Django Channels for WebSocket support
- Redis as Channels layer backend (separate from Celery queue)
- HTMX for progressive enhancement and dynamic updates
- Chart.js or Plotly.js for time-series visualization
- Bootstrap or Tailwind CSS for styling

**Real-Time Update Strategy**:

Instead of pushing every telemetry reading over WebSocket (which would be inefficient), the dashboard uses a hybrid approach:

1. **Initial Load**: HTTP request fetches recent data from TimescaleDB
2. **Periodic Polling**: HTMX polls every 2-3 seconds for updates
3. **WebSocket Notifications**: Only used for high-priority events (detected urination, system alerts)
4. **Caching**: Redis caches aggregated dashboard data (last reading per channel, summary statistics)

This approach provides <1s latency for dashboard updates while avoiding WebSocket scalability issues.

---

## Data Storage Strategy

### Single Source of Truth: TimescaleDB

All telemetry data and analytics results are stored exclusively in TimescaleDB. This eliminates complexity from duplicate storage systems.

**What's Stored in TimescaleDB**:
- Raw telemetry readings from Lightstreamer
- Detected events from analytics processors
- Processor state for replay and recovery
- Channel metadata

**What's NOT Stored Long-Term**:
- No Kafka event streams
- No message queue persistence

**Redis Usage (Ephemeral Only)**:
- Celery task queue (jobs are processed and discarded)
- Celery result backend (temporary task results)
- Django Channels layer (WebSocket message routing)
- Optional dashboard caching (short TTL)

### TimescaleDB Optimizations

**Hypertable Configuration**:
- TelemetryReading table converted to hypertable
- Automatic time-based partitioning (1-day chunks)
- Optimized for time-range queries

**Compression**:
- Automatic compression after 7 days
- Reduces storage by 10-20x
- Queries still work transparently

**Retention Policies**:
- Drop data chunks older than 30 days automatically
- Configurable per environment (longer in production if needed)

**Continuous Aggregates**:
- Pre-computed rollups for dashboard queries
- Examples: hourly averages, daily min/max, channel statistics
- Updated automatically as new data arrives

**Indexing Strategy**:
- Primary index: (channel_id, timestamp DESC) for most common query pattern
- Secondary index: (event_id) for deduplication
- Partial indexes on status_class for filtering

### Connection Pooling Architecture

**Development Setup**: Docker Compose introduces a `pgbouncer` service (session mode) between Django and TimescaleDB. PgBouncer listens on `localhost:6432`, while TimescaleDB remains exposed on `localhost:5432` for direct SQL access via psql and GUI tools.

**Django Configuration**: `CONN_MAX_AGE = 0` forces Django to close connections immediately after each request. This is optimal for PgBouncer's session pooling—PgBouncer manages the actual connection pool to PostgreSQL while Django treats each request as independent.

**Application Identification**: Each service uses a distinct `application_name` query parameter (`django-web`, `django-worker`, `django-beat`) to enable pool inspection and debugging via `SHOW CLIENTS;`.

#### Pool Sizing: Workload-Based Approach

**Development** (`default_pool_size=10`):
```
Concurrent workers analysis:
  Django runserver:     1-2 threads
  Celery workers:       2 workers
  Celery beat:          1 scheduler
  Lightstreamer:        1 async process
  Manual operations:    2-3 (migrations, dbshell, testing)
  ───────────────────────────────────
  Typical concurrent:   ~10-12 connections
  Peak with tests:      ~15 connections

Configuration:
  default_pool_size = 10       # Matches typical workload
  min_pool_size = 2           # Warm connections (no cold start)
  reserve_pool_size = 3       # Emergency buffer for bursts
  max_client_conn = 50        # 5x typical (easy leak detection)
  max_db_connections = 15     # Hard limit: 10 + 3 + 2 buffer
```

**Production** (`default_pool_size=25`):
```
Concurrent workers analysis:
  Gunicorn workers:     8 workers (WSGI)
  Daphne workers:       4 workers (ASGI/WebSocket)
  Celery workers:       4 workers
  Celery beat:          1 scheduler
  Lightstreamer:        1 async process
  Admin operations:     2-3
  ───────────────────────────────────
  Typical concurrent:   ~20-25 connections
  Peak with load:       ~30-35 connections

Configuration:
  default_pool_size = 25       # Handles typical load + buffer
  min_pool_size = 5           # More warm connections
  reserve_pool_size = 10      # Larger burst handling
  max_client_conn = 200       # High-traffic capacity
  max_db_connections = 40     # Hard limit: 25 + 10 + 5 buffer
```

#### Timeout Configuration

| Parameter | Development | Production | Purpose |
|-----------|-------------|------------|---------|
| `server_idle_timeout` | 600s (10 min) | 300s (5 min) | Reclaim idle backend connections (dev has longer gaps) |
| `server_lifetime` | 3600s (1 hour) | 3600s (1 hour) | Recycle long-lived connections (prevent leaks) |
| `query_timeout` | 30s | 60s | Kill runaway queries (tighter in dev to catch bad code) |
| `idle_transaction_timeout` | 60s | 60s | Kill forgotten transactions (prevents lock buildup) |

**Rationale**: Development uses shorter `query_timeout` (30s vs 60s) to surface bad queries early. `server_idle_timeout` is longer (10 min) because developers frequently pause work, and reconnection overhead is acceptable in dev.

#### Connection State Management

`server_reset_query = DISCARD ALL` scrubs server connections before returning to the pool:
- **Prepared statements**: Cleared (prevents statement name conflicts)
- **Temporary tables**: Dropped (prevents table name conflicts, memory leaks)
- **Advisory locks**: Released (prevents deadlocks across requests)
- **Session GUC changes**: Reset (e.g., `SET work_mem`, `SET statement_timeout`)

This is critical for session-mode pooling where connections are reused across different Django processes/requests.

#### Authentication Model

**Hybrid SCRAM Authentication**:
1. **Superuser in userlist.txt**: `pgbouncer_auth` credentials stored as SCRAM-SHA-256 hash
2. **Application users via auth_query**: `SELECT usename, passwd FROM pg_catalog.pg_shadow WHERE usename=$1`
3. **Superuser requirement**: `auth_query` needs SUPERUSER to read `pg_shadow` table

**Why this model?**:
- Application users (e.g., `peebot_user`) are created in PostgreSQL directly
- PgBouncer validates them dynamically via `auth_query` without updating `userlist.txt`
- Only the auth user (`pgbouncer_auth`) needs its hash in `userlist.txt`
- Created automatically by `docker/scripts/init-timescale.sql` on first container start

**Security Note**: In production, restrict `pgbouncer_auth` to localhost connections only (set `host` in `pg_hba.conf`).

#### Operations & Monitoring

**Admin Console Access**:
```sql
-- Connect to admin console
psql postgresql://postgres:password@localhost:6432/pgbouncer

-- View pool status
SHOW POOLS;

-- Monitor performance
SHOW STATS;

-- Inspect connections
SHOW CLIENTS;
SHOW SERVERS;

-- Reload configuration (no restart)
RELOAD;
```

**Pool Statistics Interpretation**:
- `cl_active`: Active client connections (should match concurrent workers)
- `cl_waiting`: Clients queued for connection (should be 0 in dev, <5 in prod)
- `sv_active`: Active PostgreSQL connections (should ≤ default_pool_size)
- `sv_idle`: Idle connections in pool (should be min_pool_size when idle)
- `maxwait`: Max time any client waited (should be 0; >1s indicates pool exhaustion)

**Common Issues**:
- `maxwait > 0`: Pool exhausted—check for connection leaks or increase `default_pool_size`
- `cl_waiting > 0`: Temporary spike or sustained overload—investigate slow queries
- `sv_idle = 0` when idle: `min_pool_size` not working—check config reload

#### Comparison to Direct PostgreSQL Connection

| Aspect | Direct PostgreSQL (5432) | Via PgBouncer (6432) |
|--------|--------------------------|----------------------|
| **Use case** | Admin, migrations, psql | Application code (Django, Celery) |
| **Connection cost** | High (fork + auth + init) | Low (reuses pooled connections) |
| **Max connections** | Limited by `max_connections` (100) | Unlimited clients, pooled backends |
| **Connection lifetime** | Per-worker lifetime | Pooled and recycled |
| **Statement isolation** | Full isolation | Reset between sessions |
| **Monitoring** | PostgreSQL logs | PgBouncer admin console |
| **Best for** | One-off queries, debugging | High-frequency app queries |

**Key Takeaway**: Django workers with `CONN_MAX_AGE = 0` + PgBouncer session pooling = optimal resource usage with zero connection leaks.

---

## Communication Between Modules

### 1. Polling Pattern (Primary)

Analytics modules poll the database periodically to retrieve new data:

**Flow**:
1. Celery Beat triggers periodic task (e.g., every 30 seconds)
2. Task queries ProcessorState table to get last_processed_timestamp
3. Task queries TelemetryReading for new data since last_processed_timestamp
4. Task processes data and writes results back to database
5. Task updates ProcessorState with current timestamp

**Advantages**:
- Sliding window analysis works naturally
- Independent processor schedules
- Easy historical replay
- Database is single source of truth
- No coupling between modules

### 2. Optional Django Signals (Intra-Process)

For internal notifications within the same Django process (not for analytics):

**Use Cases**:
- Notify dashboard of new events for WebSocket broadcast
- Trigger cache invalidation on data updates
- Audit logging of critical operations

**Not Used For**:
- Analytics event detection (use polling instead)
- Cross-module data processing (use polling instead)

### 3. REST APIs (Internal)

For dashboard to query data:

**Endpoints**:
- GET /api/channels/ - List all channels
- GET /api/channels/{id}/readings/ - Get readings for channel
- GET /api/events/ - List detected events
- POST /api/telemetry/inject/ - Manual data injection (testing)

---

## Deployment Architecture

### Single VPS with Coolify

**Server Specifications**:
- 4-8 CPU cores
- 16-32 GB RAM
- SSD storage
- Ubuntu 22.04 LTS

**Components Running on VPS**:

```
===================================================
              Single VPS Server
===================================================

[Nginx - Reverse Proxy]
  - SSL termination
  - Static file serving
  - WebSocket proxying
            |
            v
[Gunicorn - WSGI Server]
  - 4-8 worker processes
  - Sync workers for HTTP
            |
            v
[Daphne - ASGI Server]
  - Async workers for WebSockets
  - Django Channels routing

---------------------------------------------------

[Celery Workers]
  - 2-4 worker processes
  - Process background tasks

[Celery Beat]
  - Single scheduler process
  - Triggers periodic tasks

---------------------------------------------------

[Management Command: run_lightstreamer]
  - Long-running process
  - Supervised by systemd

---------------------------------------------------

[TimescaleDB (PostgreSQL)]
  - Single database instance
  - Regular backups

[Redis]
  - Celery broker and result backend
  - Django Channels layer
  - Optional caching

===================================================
```

**Process Management**:
- Systemd services for all long-running processes
- Automatic restart on failure
- Log aggregation to syslog or separate files

**Monitoring**:
- Prometheus + Grafana for metrics
- Sentry for error tracking
- Django Debug Toolbar in development
- Custom health check endpoints

---

## Technology Stack

### Core Framework
- **Django 5.2+**: Web framework with ORM, admin, authentication
- **Django REST Framework**: API development and serialization
- **Django Channels**: WebSocket and async support

### Database
- **TimescaleDB**: PostgreSQL extension for time-series data
- **PostgreSQL 15+**: Underlying relational database
- **pgBouncer**: Connection pooling (optional)

### Task Queue
- **Celery**: Distributed task queue
- **Celery Beat**: Periodic task scheduler
- **Redis**: Celery broker and result backend

### Real-Time
- **Django Channels**: WebSocket support
- **Redis Channels Layer**: Message routing for WebSockets
- **HTMX**: Progressive enhancement for dynamic updates

### External APIs
- **Lightstreamer Client**: ISS telemetry ingestion (custom or library)
- **Tweepy**: Twitter API integration for posting

### Frontend
- **HTMX**: Dynamic HTML updates without JavaScript frameworks
- **Chart.js** or **Plotly.js**: Time-series visualization
- **Bootstrap** or **Tailwind CSS**: Styling

### DevOps
- **Docker** + **Docker Compose**: Local development
- **Coolify**: Deployment and hosting
- **Nginx**: Reverse proxy and static files
- **Gunicorn**: WSGI server for HTTP
- **Daphne**: ASGI server for WebSockets

### Monitoring & Observability
- **Prometheus**: Metrics collection
- **Grafana**: Metrics visualization
- **Sentry**: Error tracking and alerting
- **Django Debug Toolbar**: Development debugging

---

## Performance Considerations

### Handling 10K Messages/Second

**1. Batch Inserts**: Use Django's bulk_create for efficient batch writes to database

**2. Connection Pooling**: Configure PostgreSQL connection pooling via pgBouncer or Django CONN_MAX_AGE

**3. Async Processing**: Use Django async views and async database operations for non-blocking I/O

**4. Caching Strategy**:
   - Redis cache for frequently accessed data (last reading per channel)
   - TimescaleDB continuous aggregates for pre-computed summaries
   - Short TTL (30-60 seconds) to balance freshness and performance

**5. Horizontal Scaling**:
   - Run multiple Gunicorn workers (1-2 per CPU core)
   - Run multiple Celery workers (2-4 workers)
   - Scale Daphne workers for WebSocket connections

### Database Optimization

**TimescaleDB Features**:
- Automatic time-based partitioning reduces query overhead
- Compression after 7 days reduces storage by 10-20x
- Continuous aggregates provide instant access to pre-computed rollups
- Proper indexing on (channel_id, timestamp) for common query patterns

**Query Optimization**:
- Use Django select_related() and prefetch_related() to reduce N+1 queries
- Limit result sets with pagination
- Use database-level aggregation instead of fetching all data to Python

### Latency Targets

- **Ingestion to Database**: < 5 seconds (P99)
- **Dashboard Updates**: < 1 second (P99)
- **Analytics Detection**: < 2 minutes (acceptable, runs every 30s)
- **WebSocket Message Delivery**: < 100ms

---

## Testing Strategy

### Unit Tests

**Scope**: Test individual components in isolation

**Examples**:
- Test validation service with valid and invalid telemetry data
- Test enrichment service adds correct event_id and ingested_at
- Test PeeBot detection algorithm with mock sliding window data
- Test joke generator produces valid output

**Tools**: pytest, pytest-django, model_bakery, pytest-asyncio, pytest-mock

### Integration Tests

**Scope**: Test interaction between multiple components

**Examples**:
- Test end-to-end flow from ingestion to database persistence
- Test PeeBot polling, detection, and event creation
- Test dashboard API endpoints return correct data
- Test WebSocket consumer broadcasts messages correctly

**Tools**: pytest-django, pytest-asyncio, channels.testing, model_bakery

### System Tests

**Scope**: Test complete system in production-like environment

**Examples**:
- Load test with 10K messages/second using locust or k6
- Test Lightstreamer connection handling and reconnection
- Test Celery task execution and scheduling
- Test TimescaleDB retention and compression policies

**Tools**: pytest, Docker Compose, locust or k6

### Test Database

Use separate test database with TimescaleDB enabled. Configure Django to create hypertables in test migrations.

---

## Path

### Phase 1: Setup Django Project
1. Create Django project with modular structure
2. Set up TimescaleDB and migrations
3. Implement core models and base classes
4. Configure Celery and Celery Beat

### Phase 2: Implement Ingestion Service
1. Implement Lightstreamer client as Django management command
2. Add validation service using DRF serializers
3. Add enrichment service
4. Implement repository layer for database access
5. Test manual injection endpoint

### Phase 3: Implement Storage
1. Create TelemetryReading and TelemetryChannel models
2. Set up TimescaleDB hypertable with migrations
3. Configure retention and compression policies
4. Implement custom managers for common queries
5. Add repository pattern

### Phase 4: Implement Pee-Bot
1. Implement base processor class
2. Implement PeeBot processor with detection logic
3. Add Celery periodic task
4. Integrate Twitter client
5. Add joke generation service
6. Test polling and detection

### Phase 5: Add Dashboard
1. Set up Django Channels for WebSocket support
2. Create dashboard views and templates
3. Implement WebSocket consumers
4. Add HTMX for dynamic updates
5. Integrate Chart.js for visualization
6. Test real-time updates

### Phase 6: Testing & Optimization
1. Load testing with 10K msg/sec
2. Latency optimization
3. Add monitoring with Prometheus and Grafana
4. Set up Sentry for error tracking
5. Performance tuning

### Phase 7: Deployment
1. Set up Coolify on VPS
2. Configure Nginx reverse proxy
3. Deploy with Docker Compose
4. Set up SSL certificates
5. Configure systemd services
6. Test production deployment


---
