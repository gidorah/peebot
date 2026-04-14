# PeeBot — Product Overview

**Last Updated**: 2026-01-02

---

## 1. What Is PeeBot?

PeeBot is an ISS telemetry analytics system that ingests real-time data from NASA's public Lightstreamer feed, detects when astronauts use the Urine Processor Assembly (UPA), and automatically posts humorous, AI-generated jokes to Bluesky. It turns raw spacecraft telemetry into entertainment — bridging the gap between publicly available space data and accessible public engagement.

The system is built as a **Django modular monolith** backed by **TimescaleDB**, designed for single-VPS deployment with operational simplicity as a core design goal.

---

## 2. Problem Statement

The International Space Station streams hundreds of telemetry channels in real time via Lightstreamer. This data is publicly accessible but entirely raw — numeric sensor readings with cryptic identifiers and no human-friendly context. No existing tool makes this data entertaining or relatable to a general audience.

PeeBot solves this by:

- **Ingesting** the full telemetry stream with high reliability (70 msg/sec nominal, 10K msg/sec burst-tested).
- **Detecting** meaningful events — starting with UPA tank fill patterns that indicate astronaut bathroom usage.
- **Generating** context-aware humor using an LLM (DeepSeek V3 via OpenRouter) with a "dry, scientific, slightly absurd" tone.
- **Publishing** automated posts to Bluesky with cooldown enforcement (30-minute minimum between posts).

---

## 3. Key Capabilities

| Capability | Description |
| :--- | :--- |
| **Real-Time Ingestion** | Persistent Lightstreamer connection with async bridge, Pydantic validation, smart buffering, and `abulk_create` writes to TimescaleDB. |
| **Time-Series Storage** | TimescaleDB hypertables with 1-day partitioning, 7-day compression, and 30-day retention. Single Source of Truth for all data. |
| **Event Detection** | Polling-based analytics via Celery Beat. Sliding-window trend analysis on UPA tank level (channel `NODE3000005`) every 30 seconds. |
| **Social Media Posting** | Bluesky integration via AT Protocol SDK (`atproto`). AI-generated jokes with configurable cooldown. |
| **Observability** | Structured logging (Structlog → Seq), centralized log dashboard, tagged with request/application/environment context. |

---

## 4. Target Platform

- **Deployment**: Single VPS managed by **Coolify**.
- **Architecture**: Django modular monolith — one codebase, one deployment unit.
- **Database**: PostgreSQL 16 + TimescaleDB 2.13, connection-pooled via PgBouncer (session mode).
- **Task Queue**: Celery + Redis for periodic analytics and background processing.
- **Runtime**: Python 3.14+, Django 5.2+ (LTS).

No microservices, no Kafka, no distributed infrastructure. Operational simplicity is a first-class requirement.

---

## 5. Current State

| Component | Status |
| :--- | :--- |
| **Telemetry Ingestion** | ✅ Operational — Lightstreamer client with async bridge, validation, enrichment, and buffered writes. |
| **TimescaleDB Storage** | ✅ Operational — Hypertables, compression, retention policies active. |
| **Event Detection (PeeBot)** | ✅ Active — `PeeBotProcessor` polling every 30s with sliding-window analysis. |
| **Bluesky Posting** | ✅ Integrated — AI joke generation + AT Protocol posting with cooldown enforcement. |
| **Connection Pooling** | ✅ Configured — PgBouncer with hybrid SCRAM authentication. |
| **Real-Time Dashboard** | 🔲 Planned — HTMX polling + WebSocket hybrid design specified, not yet implemented. |
| **Monitoring (Prometheus)** | 🔲 Planned — Specified in architecture, not yet deployed. |

---

## 6. Module Map

```
apps/
├── core/                  # Shared base models, utilities
├── telemetry_ingestion/   # Lightstreamer client, validation, enrichment (no models)
├── telemetry_storage/     # TelemetryReading, TelemetryChannel (data owner)
├── event_processors/      # DetectedEvent, ProcessorState, PeeBot logic, Bluesky client
└── dashboards/            # Web interface (planned)
```

Each module is a bounded context with strict model ownership. Modules communicate via database queries and Python imports — no event bus, no message broker for business logic.

---

## 7. Related Documents

- **[Architecture Specification](system-solution/architecture.md)** — Full technical design, component specs, infrastructure details.
- **[High-Level Requirements (SRS)](system-solution/high-level-requirements.md)** — Business objectives, functional/non-functional requirements, constraints.
- **[Main Tasks](system-solution/main-tasks.md)** — Project roadmap and task decomposition.
