"""Django ``AppConfig`` for ``apps.telemetry_storage``."""

from django.apps import AppConfig


class TelemetryStorageConfig(AppConfig):
    """App configuration for the storage module.

    Owns the concrete telemetry models (``TelemetryChannel``,
    ``TelemetryReading``) per ``CLAUDE.md`` Law §1.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.telemetry_storage"
