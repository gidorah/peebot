from abc import ABC, abstractmethod

from django.db.models import QuerySet

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


class TelemetryRepositoryInterface(ABC):
    @abstractmethod
    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        pass

    @abstractmethod
    async def abulk_create_readings(
        self, readings: list[TelemetryReading]
    ) -> list[TelemetryReading]:
        pass


class DjangoTelemetryRepository(TelemetryRepositoryInterface):
    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        return TelemetryChannel.objects.all()

    async def abulk_create_readings(
        self, readings: list[TelemetryReading]
    ) -> list[TelemetryReading]:
        return await TelemetryReading.objects.abulk_create(
            readings, ignore_conflicts=True
        )
