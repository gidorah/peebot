import datetime

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone
from model_bakery import baker

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading
from apps.telemetry_storage.repositories import DjangoTelemetryRepository


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

    readings = [
        TelemetryReading(
            channel=channel,
            timestamp=timezone.now(),
            value=i,
            metadata={"test": True},
        )
        for i in range(10)
    ]

    repo = DjangoTelemetryRepository()
    created_readings = await repo.abulk_create_readings(readings)

    assert len(created_readings) == 10

    count = await TelemetryReading.objects.acount()
    assert count == 10
