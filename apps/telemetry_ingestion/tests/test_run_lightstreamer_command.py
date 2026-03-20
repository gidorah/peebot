"""Tests for the run_lightstreamer management command."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from django.db import OperationalError
from django.utils import timezone

from apps.telemetry_ingestion.management.commands.run_lightstreamer import Command


def _make_command() -> Command:
    """Return a Command instance with a minimal channel_map and queue pre-initialised."""
    cmd = Command()
    cmd.channel_map = {"NODE3000005": "some-uuid"}
    cmd.queue = asyncio.Queue()
    return cmd


def _make_buffer() -> list[dict]:
    """Return a minimal enriched buffer entry matching what flush_buffer expects."""
    return [
        {
            "pui": "NODE3000005",
            "timestamp": timezone.now(),
            "value": Decimal("42.5"),
            "status_class": "normal",
            "status_indicator": "steady",
            "status_color": "green",
        }
    ]


@pytest.mark.asyncio
async def test_flush_buffer_closes_connections_on_operational_error() -> None:
    """OperationalError must close stale DB connections so the next flush gets a fresh one."""
    cmd = _make_command()
    buffer = _make_buffer()

    with (
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.TelemetryReading.objects.abulk_create",
            new_callable=AsyncMock,
            side_effect=OperationalError("server closed the connection unexpectedly"),
        ),
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.close_old_connections"
        ) as mock_close,
    ):
        await cmd.flush_buffer(buffer, queue_items_to_ack=1)

    # Broken connection must be closed so the next flush can get a fresh one.
    mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_flush_buffer_does_not_close_connections_on_other_errors() -> None:
    """Non-DB errors must NOT trigger close_old_connections (different code path)."""
    cmd = _make_command()
    buffer = _make_buffer()

    with (
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.TelemetryReading.objects.abulk_create",
            new_callable=AsyncMock,
            side_effect=ValueError("unexpected"),
        ),
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.close_old_connections"
        ) as mock_close,
    ):
        await cmd.flush_buffer(buffer, queue_items_to_ack=1)

    mock_close.assert_not_called()


@pytest.mark.asyncio
async def test_flush_buffer_acknowledges_queue_items_on_operational_error() -> None:
    """Queue items must still be ack'd after an OperationalError to prevent deadlock."""
    cmd = _make_command()
    buffer = _make_buffer()

    # Pre-populate the queue with one item so task_done() has something to ack.
    await cmd.queue.put({"NODE3000005": {}})

    with (
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.TelemetryReading.objects.abulk_create",
            new_callable=AsyncMock,
            side_effect=OperationalError("server closed the connection unexpectedly"),
        ),
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.close_old_connections"
        ),
    ):
        await cmd.flush_buffer(buffer, queue_items_to_ack=1)

    # queue.join() would block forever if task_done() was not called.
    await asyncio.wait_for(cmd.queue.join(), timeout=1.0)


@pytest.mark.asyncio
async def test_flush_buffer_logs_operational_error_at_warning() -> None:
    """Transient DB disconnects should stay visible without creating Sentry issues."""
    cmd = _make_command()
    buffer = _make_buffer()

    await cmd.queue.put({"NODE3000005": {}})

    with (
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.TelemetryReading.objects.abulk_create",
            new_callable=AsyncMock,
            side_effect=OperationalError("server closed the connection unexpectedly"),
        ),
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.close_old_connections"
        ),
        patch(
            "apps.telemetry_ingestion.management.commands.run_lightstreamer.logger"
        ) as mock_logger,
    ):
        await cmd.flush_buffer(buffer, queue_items_to_ack=1)

    mock_logger.warning.assert_called_once()
    warning_message = mock_logger.warning.call_args.args[0]
    assert "Error flushing buffer to DB" in warning_message
    mock_logger.error.assert_not_called()
