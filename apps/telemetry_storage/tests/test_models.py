import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


@pytest.mark.django_db
class TestTelemetryChannel:
    """Tests for the TelemetryChannel model."""

    def test_create_telemetry_channel(self):
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000004",
            description="Urine Processor Assembly (UPA) Output",
            ops_nom="UPA Output",
            eng_nom="UPA Output Eng",
            unit="lb/hr",
        )
        assert str(channel) == "NODE3000004 (UPA Output)"
        assert channel.created_at is not None
        assert channel.is_active is True  # From SoftDeleteModel

    def test_soft_delete_channel(self):
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000004",
            description="UPA",
            ops_nom="UPA",
            eng_nom="UPA",
            unit="lb/hr",
        )
        channel.soft_delete()
        assert TelemetryChannel.objects.count() == 0
        assert TelemetryChannel.all_objects.count() == 1
        assert channel.is_deleted is True


@pytest.mark.django_db
class TestTelemetryReading:
    """Tests for the TelemetryReading model (TimescaleDB Hypertable)."""

    def test_create_telemetry_reading_with_uuid7(self):
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000004",
            description="UPA",
            ops_nom="UPA",
            eng_nom="UPA",
            unit="lb/hr",
        )
        reading = TelemetryReading.objects.create(
            channel=channel,
            timestamp=timezone.now(),
            value=10.5,
            metadata={"source": "test"},
        )

        # Verify UUIDv7 characteristics (time-ordered version 7)
        assert reading.id is not None
        assert reading.id.version == 7
        assert reading.created_at is not None
        assert reading.value == 10.5

    def test_composite_uniqueness_constraint(self):
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000004",
            description="UPA",
            ops_nom="UPA",
            eng_nom="UPA",
            unit="lb/hr",
        )
        ts = timezone.now()
        reading = TelemetryReading.objects.create(
            channel=channel,
            timestamp=ts,
            value=10.5,
        )

        # Primary Key is (id, timestamp).
        # Since 'id' is auto-generated and unique, we test the constraint
        # by manually providing the same ID and timestamp if possible,
        # but Django's auto-id makes this hard to trigger via ORM
        # without manual ID injection.

        with pytest.raises(IntegrityError):
            TelemetryReading.objects.create(
                id=reading.id,
                channel=channel,
                timestamp=ts,
                value=20.0,
            )
