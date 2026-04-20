"""Project-wide exception hierarchy for telemetry pipeline errors.

All custom exceptions inherit from :class:`TelemetryError` so callers can
catch the whole family in one ``except`` clause. Specific subclasses exist
to let the ingestion and analytics layers distinguish validation problems
from downstream persistence or external-service failures.
"""


class TelemetryError(Exception):
    """Base class of all telemetry exceptions."""

    pass


class ValidationError(TelemetryError):
    """Raised when an incoming telemetry payload fails schema validation."""

    pass


class EnrichmentError(TelemetryError):
    """Raised when domain enrichment (e.g. timestamp normalization) fails."""

    pass


class IngestionError(TelemetryError):
    """Raised when persisting a validated reading to TimescaleDB fails."""

    pass


class ProcessorError(TelemetryError):
    """Raised when an event processor's analytics step fails unrecoverably."""

    pass


class ExternalServiceError(TelemetryError):
    """Raised when an outbound integration (OpenRouter, Bluesky) fails."""

    pass
