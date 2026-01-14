import datetime

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone
from model_bakery import baker

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading
from apps.telemetry_storage.repositories import DjangoTelemetryRepository, ReadingData


@pytest.mark.django_db
def test_get_active_channels() -> None:
    active_channel = baker.make(TelemetryChannel, deleted_at=None, public_pui="ACTIVE")
    baker.make(
        TelemetryChannel,
        deleted_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        public_pui="INACTIVE",
    )

    repo = DjangoTelemetryRepository()
    channels = repo.get_active_channels()

    assert channels.count() == 1
    assert channels.first() == active_channel


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_repository_bulk_create_async() -> None:
    channel = await sync_to_async(baker.make)(TelemetryChannel, public_pui="ASYNC_TEST")

    # Creating data dictionaries (DTOs) instead of model instances
    readings_data: list[ReadingData] = [
        {
            "channel": channel,
            "timestamp": timezone.now(),
            "value": float(i),
            "metadata": {"test": True},
        }
        for i in range(10)
    ]

    repo = DjangoTelemetryRepository()
    created_readings = await repo.abulk_create_readings(readings_data)

    assert len(created_readings) == 10

    count = await TelemetryReading.objects.acount()
    assert count == 10


@pytest.mark.django_db
def test_create_reading() -> None:
    channel = baker.make(TelemetryChannel, public_pui="TEST_CREATE")

    # Passing data dict
    reading_data: ReadingData = {
        "channel": channel,
        "timestamp": timezone.now(),
        "value": 42.0,
    }

    repo = DjangoTelemetryRepository()
    saved_reading = repo.create_reading(reading_data)

    assert saved_reading.id is not None
    assert TelemetryReading.objects.filter(id=saved_reading.id).exists()
