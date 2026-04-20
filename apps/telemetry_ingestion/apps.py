"""Django ``AppConfig`` for ``apps.telemetry_ingestion``."""

from django.apps import AppConfig


class TelemetryIngestionConfig(AppConfig):
    """App configuration for the ingestion module.

    This module intentionally owns no database models (``CLAUDE.md``
    Law §1) — it imports ``TelemetryReading`` / ``TelemetryChannel``
    from ``apps.telemetry_storage`` and writes through the shared
    repository.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.telemetry_ingestion"
