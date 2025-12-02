# Project Plan: ISS Telemetry Data Analytics System

## Epic 1: Setup Django Project
**Description:** Initialize the Django modular monolith structure, configure the database, and set up the task queue foundation.
- [ ] **Initialize Project Structure:** Create Django project with the `apps/` directory layout (core, telemetry_ingestion, telemetry_storage, event_processors, dashboards).
- [ ] **Configure TimescaleDB:** Set up PostgreSQL with TimescaleDB extension and configure Django database settings.
- [ ] **Implement Core Module:** Create `apps/core` with base abstract models (timestamps, UUIDs), utilities, and common exceptions.
- [ ] **Configure Celery Environment:** Set up Celery and Celery Beat with Redis as the broker and result backend.

## Epic 2: Implement Ingestion Service
**Description:** Build the service to connect to ISS Lightstreamer, validate incoming data, and prepare it for persistence.
- [ ] **Lightstreamer Client:** Implement the async client (management command) to connect to ISS Lightstreamer and handle subscriptions/reconnections.
- [ ] **Validation Service:** Create DRF serializers in `telemetry_ingestion` to validate incoming telemetry data types and values.
- [ ] **Enrichment Service:** Implement logic to add `event_id` (UUID) and `ingested_at` timestamps to readings.
- [ ] **Repository Integration:** Implement the repository pattern to abstract database writes (calling `telemetry_storage` logic).
- [ ] **Manual Injection Endpoint:** Create a REST API endpoint for manually injecting telemetry data for testing purposes.

## Epic 3: Implement Storage
**Description:** Implement the persistence layer with TimescaleDB optimizations for efficient time-series storage.
- [ ] **Define Models:** Create `TelemetryReading` and `TelemetryChannel` models in `apps/telemetry_storage`.
- [ ] **Hypertable Migration:** Create migrations to convert `TelemetryReading` into a TimescaleDB hypertable with 1-day partitioning.
- [ ] **Retention & Compression:** Configure automatic compression (after 7 days) and retention policies (drop after 30 days).
- [ ] **Custom Managers:** Implement Django QuerySet managers for common patterns (e.g., `get_recent`, `get_sliding_window`).
- [ ] **Repository Implementation:** Implement the actual data access methods in `apps/telemetry_storage/repositories.py`.

## Epic 4: Implement Pee-Bot (Event Processors)
**Description:** Create the analytics module that detects specific events (urination) from the telemetry stream.
- [ ] **Base Processor:** Implement `BaseProcessor` abstract class defining the polling interface and state management.
- [ ] **PeeBot Logic:** Implement `PeeBot` processor to monitor `NODE3000004` and detect fill trends using a sliding window.
- [ ] **Twitter Integration:** Create a client service to interact with the Twitter API (using `tweepy` or similar).
- [ ] **Joke Generator:** Implement a service to generate contextual humor based on telemetry values.
- [ ] **Celery Tasks:** Create and schedule the periodic Celery task (`run_pee_bot_detection`) to drive the polling.
- [ ] **Processor Models:** Define `DetectedEvent` and `ProcessorState` models in `apps/event_processors`.

## Epic 5: Add Dashboard
**Description:** Develop the real-time web interface for visualizing data and events.
- [ ] **WebSocket Setup:** Configure Django Channels and Redis Channel Layer for WebSocket support.
- [ ] **Dashboard Views:** Create standard Django views and templates for the dashboard homepage and channel details.
- [ ] **WebSocket Consumers:** Implement consumers to handle real-time data broadcasting and client subscriptions.
- [ ] **HTMX Integration:** Add HTMX to templates for dynamic partial page updates (polling/interaction).
- [ ] **Chart.js Integration:** Implement frontend logic to render time-series charts using historical data.

## Epic 6: Testing & Optimization
**Description:** Ensure system stability, performance, and correctness under load.
- [ ] **Load Testing:** Conduct load tests (e.g., with Locust) simulating 10K messages/second to verify throughput.
- [ ] **Latency Optimization:** Analyze and optimize database queries and ingestion pipeline to meet latency targets (<5s persistence).
- [ ] **Monitoring Setup:** Configure Prometheus metrics and Grafana dashboards for system observability.
- [ ] **Error Tracking:** Integrate Sentry for exception tracking and alerting.
- [ ] **Unit & Integration Tests:** Complete test coverage for all critical paths (ingestion, detection, persistence).

## Epic 7: Deployment
**Description:** Deploy the application to the production environment.
- [ ] **VPS Configuration:** Prepare the VPS with Docker, Nginx, and necessary system dependencies.
- [ ] **Coolify Setup:** Configure Coolify for application management and deployment.
- [ ] **Reverse Proxy:** Configure Nginx as the reverse proxy for HTTP and WebSocket (daphne) traffic.
- [ ] **Production Config:** Finalize production settings (security, SSL, environment variables).
- [ ] **Systemd Services:** Set up systemd units for long-running processes (if not fully dockerized via Coolify).
