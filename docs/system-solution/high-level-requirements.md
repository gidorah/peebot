# PeeBot - Software Requirements Specification (SRS)

### **1. Executive Summary**
The **PeeBot ISS Telemetry Data Analytics System** is a unified, modular monolith application designed to ingest, store, and analyze real-time telemetry data from the International Space Station (ISS). Its primary novelty function ("PeeBot") is to detect usage patterns of the Urine Processor Assembly (UPA) and automatically generate humorous, educational social media engagement via Bluesky. Beyond this, the system serves as a robust foundation for general telemetry analysis, featuring high-throughput ingestion (up to 10k msg/sec), a TimescaleDB-backed "Single Source of Truth," and a real-time WebSocket dashboard. The project prioritizes operational simplicity through a single-deployment unit architecture while ensuring scalability via asynchronous processing and independent polling-based analytics modules.

### **2. Business Objectives**
*   **BO-1:** Ingest real-time streaming telemetry data from the ISS Lightstreamer service with high reliability and zero data duplication.
*   **BO-2:** Detect specific operational events on the ISS (initially UPA tank filling) using sliding-window trend analysis.
*   **BO-3:** Automate public engagement by posting humorous, context-aware updates to Bluesky when specific events are detected.
*   **BO-4:** Provide a low-latency web dashboard for visualizing real-time telemetry, historical trends, and system events.
*   **BO-5:** Maintain a maintainable, operationally simple codebase that avoids the complexity of distributed microservices or event streaming infrastructure (Kafka).

### **3. User Personas & Stories**
*   **Persona: Space Enthusiast (Bluesky Follower)**
    *   **Description:** A member of the general public interested in space technology and humor.
    *   **User Stories:**
        *   "As a Space Enthusiast, I want to see funny posts when the ISS astronauts use the bathroom so that I feel a relatable connection to space life."
*   **Persona: Telemetry Analyst (Dashboard User)**
    *   **Description:** A user monitoring the system's data integrity and historical trends.
    *   **User Stories:**
        *   "As an Analyst, I want to browse all ~400 telemetry channels so I can explore available data points."
        *   "As an Analyst, I want to view historical charts of specific sensors to verify the accuracy of event detection."
*   **Persona: System Administrator**
    *   **Description:** DevOps engineer responsible for deploying and maintaining the VPS.
    *   **User Stories:**
        *   "As an Administrator, I want the system to be a single deployment unit so that upgrades and monitoring are simple."
        *   "As an Administrator, I want data older than 30 days to be automatically pruned so that storage costs remain predictable."

### **4. Functional Requirements (FR)**

*   **Feature: Core Infrastructure (Module: `core`)**
    *   **FR-CORE-001:** The system shall provide abstract base models for consistent UUIDv7 and timestamp tracking across all entities.
    *   **FR-CORE-002:** The system shall define centralized DRF serializers for mapping Lightstreamer field names to internal database formats.
    *   **FR-CORE-003:** The system shall handle timestamp normalization and timezone conversions for all incoming telemetry.

*   **Feature: Telemetry Ingestion (Module: `telemetry_ingestion`)**
    *   **FR-ING-001:** The system shall maintain a persistent asynchronous connection to the ISS Lightstreamer feed.
    *   **FR-ING-002:** The system shall automatically reconnect to the feed with exponential backoff upon connection loss.
    *   **FR-ING-003:** The system shall validate all incoming data packets against defined schemas (using DRF serializers) before processing.
    *   **FR-ING-004:** The system shall enrich raw data with a unique UUIDv7 event ID and a server-side ingestion timestamp (`ingested_at`).
    *   **FR-ING-005:** The system shall persist valid readings to the database immediately, using batch inserts for performance.
    *   **FR-ING-006:** The system shall provide a restricted REST API endpoint for manual injection of telemetry data for testing purposes.

*   **Feature: Data Storage (Module: `telemetry_storage`)**
    *   **FR-STO-001:** The system shall store all telemetry readings in a TimescaleDB hypertable partitioned by time (1-day chunks).
    *   **FR-STO-002:** The system shall automatically compress data chunks older than 7 days.
    *   **FR-STO-003:** The system shall automatically delete data chunks older than 30 days (Retention Policy).
    *   **FR-STO-004:** The system shall ensure data uniqueness based on the composite key of `id` and `timestamp`.
    *   **FR-STO-005:** The system shall maintain metadata for ~400 telemetry channels, including Public PUI, nomenclature (Ops/Eng), and units.

*   **Feature: Event Processing - PeeBot (Module: `event_processors`)**
    *   **FR-PROC-001:** The system shall execute analytics modules independently via a polling mechanism (Celery Beat) rather than event streams.
    *   **FR-PROC-002:** The PeeBot processor shall query the `TelemetryReading` table every 30 seconds for new data on channel `NODE3000004` (UPA Tank Level).
    *   **FR-PROC-003:** The processor shall detect a "Fill Event" by analyzing the sliding window of the last 10 minutes for a consistent increasing trend.
    *   **FR-PROC-004:** Upon detection, the system shall generate "dry, scientific, slightly absurd" humorous text using an integration with an external LLM API.
    *   **FR-PROC-005:** The system shall post the generated text to Bluesky via the AT Protocol API, subject to a minimum 30-minute cooldown period between posts.

*   **Feature: Real-Time Dashboard (Module: `dashboards`)**
    *   **FR-DASH-001:** The system shall provide a web interface displaying live status of key telemetry channels.
    *   **FR-DASH-002:** The dashboard shall include a searchable browser for all telemetry channels (~400).
    *   **FR-DASH-003:** The system shall allow for dynamic selection of "high-priority" channels which will receive real-time updates via WebSockets.
    *   **FR-DASH-004:** The dashboard shall use HTMX polling (2-3s interval) for all non-priority channel updates to minimize WebSocket load.
    *   **FR-DASH-005:** The system shall provide interactive time-series charts for historical data visualization (using Chart.js or similar).

### **5. Non-Functional Requirements (NFR)**

*   **Performance (NFR-PERF)**
    *   **NFR-PERF-001:** The system shall support a nominal throughput of 70 messages/second and burst capacity up to 10,000 messages/second.
    *   **NFR-PERF-002:** Ingestion latency (Time from receipt to DB persistence) shall be < 5 seconds (P99).
    *   **NFR-PERF-003:** Dashboard update latency shall be < 1 second (P99).
    *   **NFR-PERF-004:** Analytics detection time (Time from event occurrence to detection) shall be < 2 minutes.

*   **Architecture & Maintainability (NFR-ARCH)**
    *   **NFR-ARCH-001:** The system must adhere to the Modular Monolith pattern; modules must not import models from other modules (except via strictly defined ownership rules).
    *   **NFR-ARCH-002:** The database (TimescaleDB) shall be the "Single Source of Truth"; no intermediate persistent queues (like Kafka) shall be used.
    *   **NFR-ARCH-003:** All database connections must be pooled (e.g., via PgBouncer) to support high concurrency.

*   **Reliability (NFR-REL)**
    *   **NFR-REL-001:** The system shall gracefully handle upstream data interruptions without crashing.
    *   **NFR-REL-002:** Analytics modules must store their state (`last_processed_at`) to allow for resumption and historical replay.

### **6. Assumptions & Constraints**
*   **C-001:** The system must be built using Python 3.14+, Django 5.2+, and TimescaleDB.
*   **C-002:** Deployment target is a single VPS managed by Coolify.
*   **C-003:** No Kafka or complex event streaming infrastructure is permitted.
*   **C-004:** The Bluesky API usage must respect the AT Protocol rate limits unless otherwise specified.
*   **A-001:** It is assumed that the Lightstreamer connection library is available or can be custom-implemented.
*   **A-002:** The specific LLM provider for the Joke Generator will be selected during the implementation phase, but the architecture must support a generic API integration.

### **7. Out of Scope**
*   **OOS-001:** Microservices architecture.
*   **OOS-002:** Long-term archival of raw telemetry data beyond 30 days (unless aggregated).
*   **OOS-003:** User authentication for the public dashboard (it is read-only public).
*   **OOS-004:** Two-way control of ISS systems (Read-only data).

### **8. Clarifying Questions**
*   **Technical (Q-1):** "Hybrid SCRAM Authentication" is specified for PgBouncer. Does the production environment (Coolify) support the necessary volume mounts for `userlist.txt` management?
