"""
Restart-simulation tests for duplicate ingestion prevention (T004 / FR-DEDUP-002).

Tests flush_buffer directly against a real DB to confirm that:
  1. A second flush containing the same (channel, timestamp) reading does not raise.
  2. Only one row is persisted after both flushes.
  3. Genuinely new readings in the same batch as duplicates are still persisted.
"""

import asyncio

import pytest
from django.utils import timezone
from model_bakery import baker

from apps.telemetry_ingestion.management.commands.run_lightstreamer import Command
from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


def _make_enriched(pui: str, ts: object, value: float) -> dict:
    """Return a minimal enriched-data dict as produced by TelemetryEnricher."""
    return {
        "pui": pui,
        "timestamp": ts,
        "value": value,
        "status_class": None,
        "status_indicator": None,
        "status_color": None,
    }


@pytest.fixture
def command_with_channel(db):  # type: ignore[no-untyped-def]
    """Synchronous fixture: creates a channel and wires up a Command instance."""
    channel = baker.make(TelemetryChannel, public_pui="RESTART_TEST")
    cmd = Command()
    cmd.queue = asyncio.Queue()  # not used by flush_buffer but required by __init__
    cmd.channel_map = {"RESTART_TEST": channel.pk}
    return cmd, channel


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_restart_simulation_no_exception(command_with_channel) -> None:  # type: ignore[no-untyped-def]
    """
    FR-DEDUP-002: Two consecutive flushes of the same (channel, timestamp) reading
    must not raise any exception.
    """
    cmd, _ = command_with_channel
    ts = timezone.now()
    batch = [_make_enriched("RESTART_TEST", ts, 42.0)]

    # First flush — should succeed normally
    await cmd.flush_buffer(batch, queue_items_to_ack=0)

    # Second flush — same reading, must be silently ignored
    await cmd.flush_buffer(batch, queue_items_to_ack=0)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_restart_simulation_exactly_one_row(command_with_channel) -> None:  # type: ignore[no-untyped-def]
    """
    FR-DEDUP-001/002: After two flushes of the same reading, exactly one DB row exists.
    """
    cmd, channel = command_with_channel
    ts = timezone.now()
    batch = [_make_enriched("RESTART_TEST", ts, 42.0)]

    await cmd.flush_buffer(batch, queue_items_to_ack=0)
    await cmd.flush_buffer(batch, queue_items_to_ack=0)

    count = await TelemetryReading.objects.filter(
        channel=channel, timestamp=ts
    ).acount()
    assert count == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_restart_simulation_new_readings_still_persisted(
    command_with_channel,
) -> None:  # type: ignore[no-untyped-def]
    """
    FR-DEDUP-003: A batch that contains both a duplicate and a genuinely new reading
    must persist the new reading while silently skipping the duplicate.
    """
    cmd, channel = command_with_channel
    ts_old = timezone.now()
    ts_new = timezone.now()
    # Ensure timestamps are distinct even if clock resolution is low
    while ts_new == ts_old:
        ts_new = timezone.now()

    first_batch = [_make_enriched("RESTART_TEST", ts_old, 1.0)]
    second_batch = [
        _make_enriched("RESTART_TEST", ts_old, 1.0),  # duplicate
        _make_enriched("RESTART_TEST", ts_new, 2.0),  # genuinely new
    ]

    await cmd.flush_buffer(first_batch, queue_items_to_ack=0)
    await cmd.flush_buffer(second_batch, queue_items_to_ack=0)

    total = await TelemetryReading.objects.acount()
    assert total == 2

    old_count = await TelemetryReading.objects.filter(
        channel=channel, timestamp=ts_old
    ).acount()
    assert old_count == 1

    new_count = await TelemetryReading.objects.filter(
        channel=channel, timestamp=ts_new
    ).acount()
    assert new_count == 1
