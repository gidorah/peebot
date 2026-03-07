from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from apps.telemetry_storage.models import TelemetryChannel
from apps.telemetry_storage.repositories import ReadingData


class ManualInjectionPayload(BaseModel):
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
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value

    def to_reading_data(self, channel: TelemetryChannel) -> ReadingData:
        return {
            "channel": channel,
            "timestamp": self.timestamp,
            "value": self.value,
            "calibrated_data": self.calibrated_data,
            "status_class": self.status_class,
            "status_indicator": self.status_indicator,
            "status_color": self.status_color,
        }
