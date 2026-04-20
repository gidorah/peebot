"""Shared utility helpers for the ``core`` module.

Per ``ADR-007`` (Hybrid Enrichment Strategy) the production
responsibilities originally sketched for this module live elsewhere:

* Timestamp normalization (UTC / year rollover) is owned by
  ``apps.telemetry_ingestion.services.enricher``.
* Event ID generation (UUIDv7) is provided by ``UUID7Model`` in
  ``apps.core.models`` as a model-level default.

The functions below are retained as intentional placeholders for potential
future reuse. They have no callers today and MUST NOT be relied on without
first confirming they match the behavior documented in the architecture
specification (``docs/system-solution/architecture.md`` §8.1).
"""

from uuid import UUID, uuid4


def generate_event_id() -> UUID:
    """Return a random UUID4 suitable for ad-hoc event identifiers.

    Production event IDs are produced by ``UUID7Model`` for time-sortable
    primary keys. Prefer that pattern for database-bound entities; use this
    helper only for non-persisted identifiers where UUID4 randomness is
    acceptable.

    Returns:
        UUID: A freshly generated random UUID (version 4).
    """
    return uuid4()


def normalize_timestamp() -> None:
    """Placeholder for timestamp normalization (UTC / year rollover).

    Not implemented. The production implementation lives in
    ``apps.telemetry_ingestion.services.enricher`` per ADR-007, where domain
    normalization is colocated with the ingestion hot path.
    """
    pass


def safe_decimal() -> None:
    """Placeholder for safe string-to-``Decimal`` coercion with fallback.

    Not implemented. Ingestion-path coercion currently runs through Pydantic
    validators on ``LightstreamerReading`` per ADR-004.
    """
    pass


def chunk_list() -> None:
    """Placeholder for splitting iterables into fixed-size batches.

    Not implemented. Batch flushing in the ingestion pipeline is handled by
    the bounded in-memory buffer in the ``run_lightstreamer`` management
    command rather than a generic chunking helper.
    """
    pass
