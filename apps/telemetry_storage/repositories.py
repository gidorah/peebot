from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict, cast

from django.db.models import QuerySet

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


class ReadingData(TypedDict, total=False):
    channel: TelemetryChannel
    timestamp: datetime
    value: float | Decimal
    calibrated_data: float | Decimal | None
    status_class: str | None
    status_indicator: str | None
    status_color: str | None
    metadata: dict[str, Any] | None


class TelemetryRepositoryInterface(ABC):
    @abstractmethod
    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        pass

    @abstractmethod
    async def abulk_create_readings(
        self, readings_data: list[ReadingData]
    ) -> list[TelemetryReading]:
        pass

    @abstractmethod
    def create_reading(self, reading_data: ReadingData) -> TelemetryReading:
        pass


class DjangoTelemetryRepository(TelemetryRepositoryInterface):
    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        return TelemetryChannel.objects.all()

    async def abulk_create_readings(
        self, readings_data: list[ReadingData]
    ) -> list[TelemetryReading]:
        readings = [TelemetryReading(**data) for data in readings_data]
        return cast(
            list[TelemetryReading],
            await TelemetryReading.objects.abulk_create(  # type: ignore[attr-defined]
                readings, ignore_conflicts=True
            ),
        )

    def create_reading(self, reading_data: ReadingData) -> TelemetryReading:
        return cast(
            TelemetryReading,
            TelemetryReading.objects.create(**reading_data),  # type: ignore[attr-defined]
        )
