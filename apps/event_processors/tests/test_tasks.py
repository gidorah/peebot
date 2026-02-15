"""Tests for event processor Celery tasks.

Verifies the full orchestration flow of the PeeBot processor task,
including data querying, analysis, event creation, external service
triggers, and error handling.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.db import OperationalError
from django.utils import timezone
from model_bakery import baker

from apps.event_processors.models import DetectedEvent, ProcessorState
from apps.event_processors.tasks import run_peebot_processor
from apps.telemetry_storage.models import TelemetryReading


@pytest.mark.django_db(transaction=True)
class TestRunPeeBotProcessor:
    """Tests for the run_peebot_processor task."""

    @pytest.fixture(autouse=True)
    def setup_method(self) -> None:
        """Setup common mocks for each test."""
        # Mock the processor's jitter to avoid delays
        self.jitter_patch = patch(
            "apps.event_processors.processors.base.BaseProcessor.apply_jitter",
            new_callable=AsyncMock,
        )
        self.jitter_mock = self.jitter_patch.start()

        # Mock external services (patch at import site since tasks.py imports at module level)
        self.joke_gen_patch = patch("apps.event_processors.tasks.JokeGenerator")
        self.bluesky_patch = patch("apps.event_processors.tasks.BlueskyClient")
        self.mock_joke_gen_class = self.joke_gen_patch.start()
        self.mock_bluesky_class = self.bluesky_patch.start()

        self.mock_joke_gen = MagicMock()
        self.mock_joke_gen.generate = AsyncMock(return_value="Test joke")
        self.mock_joke_gen_class.return_value = self.mock_joke_gen

        self.mock_bluesky = MagicMock()
        self.mock_bluesky.check_cooldown = AsyncMock(return_value=(True, None))
        self.mock_bluesky.post = AsyncMock(
            return_value="at://did:plc:xxx/app.bsky.feed.post/123"
        )
        self.mock_bluesky_class.return_value = self.mock_bluesky

    def test_run_peebot_processor_happy_path(self) -> None:
        """Task successfully detects event and posts to Bluesky."""
        # 1. Setup data: processor state and telemetry readings (increasing trend)
        state = baker.make(
            ProcessorState, processor_name="pee_bot", last_processed_timestamp=None
        )

        # Create channel
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000004"
        )

        # Create readings showing a burst (30s duration, 1% increase)
        now = timezone.now()
        readings = []
        for i in range(11):  # 30 seconds at 3s intervals
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = Decimal("10.0") + Decimal(str(i * 0.1))
            readings.append(
                baker.make(
                    TelemetryReading,
                    channel=channel,
                    timestamp=ts,
                    value=val,
                    calibrated_data=val,
                )
            )

        # 2. Run task
        result = run_peebot_processor()

        # 3. Assertions
        assert result["event_detected"] is True
        assert result["post_published"] is True
        assert result["error"] is None

        # Verify DetectedEvent created
        event = DetectedEvent.objects.get(event_type="urination")
        assert event.channel_id == "NODE3000004"
        assert event.confidence > 0

        # Verify state updated
        state.refresh_from_db()
        assert state.last_processed_timestamp is not None
        assert state.last_run_at is not None

        # Verify external calls
        self.mock_joke_gen.generate.assert_called_once()
        self.mock_bluesky.post.assert_called_once()

    def test_run_peebot_processor_no_event(self) -> None:
        """Task runs but detects no event with flat readings."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000004"
        )

        now = timezone.now()
        # Flat readings
        for i in range(5):
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=now - timedelta(seconds=i * 10),
                value=Decimal("10.0"),
            )

        result = run_peebot_processor()

        assert result["event_detected"] is False
        assert result["post_published"] is False
        assert DetectedEvent.objects.count() == 0

    def test_run_peebot_processor_cooldown_blocks_post(self) -> None:
        """Task detects event but respects Bluesky cooldown."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000004"
        )

        # Readings showing a burst
        now = timezone.now()
        for i in range(11):
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = Decimal("10.0") + Decimal(str(i * 0.1))
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=ts,
                value=val,
                calibrated_data=val,
            )

        # Simulate cooldown active by making post() raise BlueskyCooldownError
        from apps.event_processors.services.bluesky_client import BlueskyCooldownError

        self.mock_bluesky.post.side_effect = BlueskyCooldownError(
            "Cannot post: cooldown active. Wait 15.0 more minutes."
        )

        result = run_peebot_processor()

        assert result["event_detected"] is True
        assert result["post_published"] is False
        assert DetectedEvent.objects.count() == 1
        self.mock_bluesky.post.assert_called_once()

    def test_run_peebot_processor_db_error_triggers_retry(self) -> None:
        """OperationalError causes task to retry via exception propagation."""
        baker.make(ProcessorState, processor_name="pee_bot")

        # Mock load_state to raise OperationalError
        with patch(
            "apps.event_processors.processors.pee_bot.PeeBotProcessor.load_state",
            side_effect=OperationalError("DB down"),
        ):
            # When calling task directly or with delay().get(),
            # it should raise OperationalError if retries are exhausted
            # or if we don't mock the retry mechanism itself.
            # pytest-celery can test retries more thoroughly,
            # but here we just check it raises.
            with pytest.raises(OperationalError):
                run_peebot_processor()

    def test_run_peebot_processor_general_exception_swallowed(self) -> None:
        """General exceptions are logged but don't crash the task execution cycle."""
        baker.make(ProcessorState, processor_name="pee_bot")

        with patch(
            "apps.event_processors.processors.pee_bot.PeeBotProcessor.analyze",
            side_effect=Exception("Unexpected failure"),
        ):
            # Create some readings to trigger analyze
            channel: Any = baker.make(
                "telemetry_storage.TelemetryChannel", public_pui="NODE3000004"
            )
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=timezone.now(),
                value=Decimal("10.0"),
            )

            result = run_peebot_processor()

            assert result["error"] == "Unexpected failure"
            assert result["event_detected"] is False

            # Verify state.last_run_at was still updated
            state = ProcessorState.objects.get(processor_name="pee_bot")
            assert state.last_run_at is not None

    def test_run_peebot_processor_joke_gen_failure(self) -> None:
        """Task handles joke generation failure gracefully."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000004"
        )

        # Burst readings
        now = timezone.now()
        for i in range(11):
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = Decimal("10.0") + Decimal(str(i * 0.1))
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=ts,
                value=val,
                calibrated_data=val,
            )

        # Mock joke generation returning None
        self.mock_joke_gen.generate.return_value = None

        result = run_peebot_processor()

        assert result["event_detected"] is True
        assert result["post_published"] is False
        self.mock_bluesky.post.assert_not_called()

    def test_run_peebot_processor_cursor_advances_past_burst(self) -> None:
        """Cursor is set to latest reading timestamp (not burst start) after detection."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000004"
        )

        # Create burst readings
        now = timezone.now()
        readings = []
        for i in range(11):
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = Decimal("10.0") + Decimal(str(i * 0.1))
            readings.append(
                baker.make(
                    TelemetryReading,
                    channel=channel,
                    timestamp=ts,
                    value=val,
                    calibrated_data=val,
                )
            )

        result = run_peebot_processor()
        assert result["event_detected"] is True

        # Verify cursor is at latest reading, not burst start
        state = ProcessorState.objects.get(processor_name="pee_bot")
        latest_reading_ts = max(r.timestamp for r in readings)
        event = DetectedEvent.objects.get(event_type="urination")

        # Cursor must be at or after the latest reading (not at burst start)
        assert state.last_processed_timestamp >= latest_reading_ts
        assert state.last_processed_timestamp > event.detected_at
