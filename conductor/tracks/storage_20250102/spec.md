# Track Spec: Implement Telemetry Storage Module

## Objective
Implement the `apps/telemetry_storage` module to serve as the "Single Source of Truth" for all telemetry data. This includes defining the Django models, configuring the TimescaleDB hypertable, and implementing a Repository pattern to abstract database access.

## Scope
-   **Models:**
    -   `TelemetryChannel`: Metadata for each telemetry sensor, derived from `docs/PUIList.xml`.
        -   Fields:
            -   `id`: AutoField (primary key)
            -   `public_pui`: CharField (unique, e.g., "NODE3000004") (Public Program Unique Identifier)
            -   `description`: CharField
            -   `ops_nom`: CharField (Operations Nomenclature)
            -   `eng_nom`: CharField (Engineering Nomenclature)
            -   `unit`: CharField
            -   `is_active`: BooleanField (default False, except NODE3000004)
            -   `created_at`: DateTimeField
            -   `updated_at`: DateTimeField
    -   `TelemetryReading`: Time-series data points (Hypertable).
        -   Fields:
            -   `id`: UUIDv7 (primary key)
            -   `channel`: ForeignKey -> TelemetryChannel
            -   `timestamp`: DateTimeField (indexed)
            -   `value`: DecimalField
            -   `calibrated_data`: DecimalField (optional)
            -   `status_class`: CharField (optional)
            -   `status_indicator`: CharField (optional)
            -   `status_color`: CharField (optional)
            -   `ingested_at`: DateTimeField
-   **Database:**
    -   Configure `TelemetryReading` as a TimescaleDB hypertable partitioned by time (1-day chunks).
    -   Set up compression policies (compress after 7 days).
    -   Set up retention policies (drop after 30 days).
    -   Indexes:
        -   Primary: `(channel, timestamp DESC)`
        -   Secondary: `(ingested_at)`
-   **Repository:**
    -   Create `TelemetryRepository` to handle standard CRUD and specialized bulk insert operations.
    -   Ensure isolation: Downstream modules (ingestion, processors) must use this repository, not the ORM directly.
-   **Seeding:**
    -   Create a management command `seed_channels` to parse `docs/PUIList.xml` and populate `TelemetryChannel`.
    -   Ensure only `NODE3000004` (UPA) is set to `is_active=True`.
-   **Testing:**
    -   Unit tests for model constraints and methods.
    -   Integration tests for the Repository layer using `pytest-django`.
    -   Test seeding command logic.

## Technical Constraints
-   **Strict Typing:** Use `mypy --strict`.
-   **Async First:** The repository must support async access (e.g., `abulk_create`) for the ingestion pipeline.
-   **TimescaleDB:** Must use the `timescale` Django library or raw SQL migrations for hypertable setup.
-   **XML Parsing:** Use `defusedxml` or `xml.etree.ElementTree` securely for seeding.

## Success Criteria
1.  Migrations apply successfully and create a valid Hypertable in TimescaleDB.
2.  `seed_channels` command correctly populates all channels from PUIList.xml with correct schema mapping.
3.  Only `NODE3000004` is active after seeding.
4.  `TelemetryRepository` can successfully insert 10,000 readings in a single bulk operation.
5.  Unit tests pass with >80% coverage.
