"""Tests for ``TelemetryChannel`` and ``TelemetryReading`` model behavior and constraints."""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


@pytest.mark.django_db
class TestTelemetryChannel:
    """Tests for the TelemetryChannel model."""

    def test_create_telemetry_channel(self):
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000005",
            description="Urine Processor Assembly (UPA) Output",
            ops_nom="UPA Output",
            eng_nom="UPA Output Eng",
            unit="lb/hr",
        )
        assert str(channel) == "NODE3000005 (UPA Output)"
        assert channel.created_at is not None
        assert channel.is_active is True  # From SoftDeleteModel

    def test_soft_delete_channel(self):
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000005",
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
            public_pui="NODE3000005",
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

    def test_unique_channel_timestamp_constraint(self):
        """FR-DEDUP-001: at most one reading per (channel, timestamp) pair."""
        channel = TelemetryChannel.objects.create(
            public_pui="NODE3000005",
            description="UPA",
            ops_nom="UPA",
            eng_nom="UPA",
            unit="lb/hr",
        )
        ts = timezone.now()
        TelemetryReading.objects.create(
            channel=channel,
            timestamp=ts,
            value=10.5,
        )

        with pytest.raises(IntegrityError):
            # Same channel + same timestamp → must violate unique_channel_timestamp
            TelemetryReading.objects.create(
                channel=channel,
                timestamp=ts,
                value=20.0,
            )
