"""Pydantic payload schema for the manual telemetry injection endpoint.

Backs ``POST /api/v1/telemetry/inject/`` (FR-ING-006). The endpoint is
gated by :class:`~apps.core.permissions.IsDebugMode` and is intended for
development / debugging only; production deployments leave it disabled.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from apps.telemetry_storage.models import TelemetryChannel
from apps.telemetry_storage.repositories import ReadingData


class ManualInjectionPayload(BaseModel):
    """Validated request body for manual telemetry injection.

    ``extra="forbid"`` ensures callers get a clear error when sending
    unknown fields — useful for catching copy/paste mistakes in ad-hoc
    debugging requests.
    """

    model_config = ConfigDict(extra="forbid")

    pui: str
    timestamp: datetime
    value: Decimal
    calibrated_data: Decimal | None = None
    status_class: str | None = None
    status_indicator: str | None = None
    status_color: str | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        """Reject naive datetimes so every persisted reading is timezone-aware.

        Mirrors the invariant maintained by the live Lightstreamer
        pipeline via :class:`~apps.telemetry_ingestion.services.enricher.TelemetryEnricher`.

        Args:
            value: The datetime to validate.

        Returns:
            The original datetime, unchanged, when timezone-aware.

        Raises:
            ValueError: If ``value.tzinfo`` is ``None``.
        """
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value

    def to_reading_data(self, channel: TelemetryChannel) -> ReadingData:
        """Project this payload onto the repository's :class:`ReadingData` shape.

        Args:
            channel: Resolved :class:`TelemetryChannel` matching ``self.pui``
                (looked up by the caller before invoking this method).

        Returns:
            A dict suitable for
            :meth:`~apps.telemetry_storage.repositories.DjangoTelemetryRepository.create_reading`.
        """
        return {
            "channel": channel,
            "timestamp": self.timestamp,
            "value": self.value,
            "calibrated_data": self.calibrated_data,
            "status_class": self.status_class,
            "status_indicator": self.status_indicator,
            "status_color": self.status_color,
        }
