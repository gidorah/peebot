from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict

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
    def get_channel_by_public_pui(self, public_pui: str) -> TelemetryChannel | None:
        pass

    @abstractmethod
    async def abulk_create_readings(
        self, readings_data: list[ReadingData]
    ) -> list[TelemetryReading]:
        pass

    @abstractmethod
    def create_reading(self, reading_data: ReadingData) -> TelemetryReading:
        pass


def get_telemetry_channel_queryset() -> QuerySet[TelemetryChannel]:
    return DjangoTelemetryRepository().get_active_channels()


class DjangoTelemetryRepository(TelemetryRepositoryInterface):
    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        return TelemetryChannel.objects.order_by("public_pui")

    def get_channel_by_public_pui(self, public_pui: str) -> TelemetryChannel | None:
        return TelemetryChannel.objects.filter(public_pui=public_pui).first()

    async def abulk_create_readings(
        self, readings_data: list[ReadingData]
    ) -> list[TelemetryReading]:
        readings = [TelemetryReading(**data) for data in readings_data]
        return await TelemetryReading.objects.abulk_create(
            readings, ignore_conflicts=True
        )

    def create_reading(self, reading_data: ReadingData) -> TelemetryReading:
        return TelemetryReading.objects.create(**reading_data)
