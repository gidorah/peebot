class TelemetryError(Exception):
    """
    Base class of all telemetry exceptions
    """

    pass


class ValidationError(TelemetryError):
    pass


class EnrichmentError(TelemetryError):
    pass


class IngestionError(TelemetryError):
    pass


class ProcessorError(TelemetryError):
    pass


class ExternalServiceError(TelemetryError):
    pass
