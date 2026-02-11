"""Integration tests for event_processors module.

Tests the full PeeBot processor flow with realistic telemetry data,
verifying end-to-end event detection without mocking core processor logic.

Only external services (Bluesky, LLM) are mocked.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.utils import timezone
from model_bakery import baker

from apps.event_processors.models import DetectedEvent, ProcessorState
from apps.event_processors.tasks import run_peebot_processor
from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading

if TYPE_CHECKING:
    from collections.abc import Generator


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def upa_channel() -> TelemetryChannel:
    """Create the UPA Tank Level channel (NODE3000004)."""
    return baker.make(
        TelemetryChannel,
        public_pui="NODE3000004",
        description="UPA Waste Water Tank Quantity",
        ops_nom="UPA WW TK QTY",
        eng_nom="Node 3 UPA Wastewater Tank",
        unit="%",
    )


@pytest.fixture
def processor_state() -> ProcessorState:
    """Create a fresh processor state for pee_bot."""
    return baker.make(
        ProcessorState,
        processor_name="pee_bot",
        last_processed_timestamp=None,
        last_run_at=None,
        state_data={},
    )


@pytest.fixture
def mock_external_services() -> Generator[dict[str, MagicMock]]:
    """Mock external services (Bluesky, JokeGenerator) but NOT processor logic."""
    with (
        patch(
            "apps.event_processors.processors.base.BaseProcessor.apply_jitter",
            new_callable=AsyncMock,
        ) as jitter_mock,
        patch(
            "apps.event_processors.services.joke_generator.JokeGenerator"
        ) as joke_gen_class,
        patch(
            "apps.event_processors.services.bluesky_client.BlueskyClient"
        ) as bluesky_class,
    ):
        mock_joke_gen = MagicMock()
        mock_joke_gen.generate = AsyncMock(
            return_value="Astronaut hydration metrics nominal. Tank levels rising."
        )
        joke_gen_class.return_value = mock_joke_gen

        mock_bluesky = MagicMock()
        mock_bluesky.check_cooldown = AsyncMock(return_value=(True, None))
        mock_bluesky.post = AsyncMock(
            return_value="at://did:plc:xxx/app.bsky.feed.post/123456789"
        )
        bluesky_class.return_value = mock_bluesky

        yield {
            "jitter": jitter_mock,
            "joke_generator": mock_joke_gen,
            "bluesky_client": mock_bluesky,
        }


# =============================================================================
# Test Data Helpers
# =============================================================================


def create_burst_readings(
    channel: TelemetryChannel,
    *,
    burst_duration_seconds: int = 45,
    baseline: Decimal = Decimal("25.0"),
    delta_per_reading: Decimal = Decimal("0.15"),
    interval_seconds: int = 3,
    start_offset_seconds: int = 120,
) -> list[TelemetryReading]:
    """Create readings simulating a sustained burst (fill event).

    Pattern:
    1. Pre-burst baseline (30 seconds)
    2. Sustained increase over burst_duration_seconds
    3. Post-burst stabilization (15 seconds at new level)

    Args:
        channel: The telemetry channel to associate readings with.
        burst_duration_seconds: Duration of the increasing trend.
        baseline: Starting tank level percentage.
        delta_per_reading: How much level increases per reading during burst.
        interval_seconds: Time between readings.
        start_offset_seconds: How far back from now to start the pattern.

    Returns:
        List of created TelemetryReading objects.
    """
    now = timezone.now()
    readings = []
    current_time = now - timedelta(seconds=start_offset_seconds)

    # Phase 1: Pre-burst baseline (30 seconds)
    pre_burst_readings = 30 // interval_seconds
    for _ in range(pre_burst_readings):
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=baseline,
                calibrated_data=baseline,
                status_class="normal",
            )
        )
        current_time += timedelta(seconds=interval_seconds)

    # Phase 2: Sustained burst (increasing trend)
    burst_readings_count = burst_duration_seconds // interval_seconds
    current_value = baseline
    for _ in range(burst_readings_count):
        current_value += delta_per_reading
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=current_value,
                calibrated_data=current_value,
                status_class="normal",
            )
        )
        current_time += timedelta(seconds=interval_seconds)

    # Phase 3: Post-burst stabilization (15 seconds at new level)
    post_burst_readings = 15 // interval_seconds
    stable_value = current_value
    for _ in range(post_burst_readings):
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=stable_value,
                calibrated_data=stable_value,
                status_class="normal",
            )
        )
        current_time += timedelta(seconds=interval_seconds)

    return readings


def create_glitch_readings(
    channel: TelemetryChannel,
    *,
    baseline: Decimal = Decimal("25.0"),
    spike_value: Decimal = Decimal("30.0"),
    interval_seconds: int = 3,
    start_offset_seconds: int = 60,
) -> list[TelemetryReading]:
    """Create readings simulating a sensor glitch (spike that immediately reverts).

    Pattern:
    1. Baseline readings (15 seconds)
    2. Single spike reading
    3. Immediate revert to baseline (15 seconds)

    This pattern should NOT trigger an event.
    """
    now = timezone.now()
    readings = []
    current_time = now - timedelta(seconds=start_offset_seconds)

    # Phase 1: Pre-spike baseline
    pre_spike_readings = 15 // interval_seconds
    for _ in range(pre_spike_readings):
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=baseline,
                calibrated_data=baseline,
                status_class="normal",
            )
        )
        current_time += timedelta(seconds=interval_seconds)

    # Phase 2: Single spike
    readings.append(
        baker.make(
            TelemetryReading,
            channel=channel,
            timestamp=current_time,
            value=spike_value,
            calibrated_data=spike_value,
            status_class="normal",
        )
    )
    current_time += timedelta(seconds=interval_seconds)

    # Phase 3: Immediate revert to baseline
    post_spike_readings = 15 // interval_seconds
    for _ in range(post_spike_readings):
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=baseline,
                calibrated_data=baseline,
                status_class="normal",
            )
        )
        current_time += timedelta(seconds=interval_seconds)

    return readings


def create_flat_readings(
    channel: TelemetryChannel,
    *,
    value: Decimal = Decimal("25.0"),
    count: int = 20,
    interval_seconds: int = 3,
    start_offset_seconds: int = 60,
) -> list[TelemetryReading]:
    """Create flat readings with no trend.

    This pattern should NOT trigger an event.
    """
    now = timezone.now()
    readings = []
    current_time = now - timedelta(seconds=start_offset_seconds)

    for _ in range(count):
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=value,
                calibrated_data=value,
                status_class="normal",
            )
        )
        current_time += timedelta(seconds=interval_seconds)

    return readings


def create_decreasing_readings(
    channel: TelemetryChannel,
    *,
    start_value: Decimal = Decimal("30.0"),
    delta_per_reading: Decimal = Decimal("0.1"),
    count: int = 20,
    interval_seconds: int = 3,
    start_offset_seconds: int = 60,
) -> list[TelemetryReading]:
    """Create readings with a decreasing trend (UPA processing).

    This pattern should NOT trigger an event.
    """
    now = timezone.now()
    readings = []
    current_time = now - timedelta(seconds=start_offset_seconds)
    current_value = start_value

    for _ in range(count):
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=current_time,
                value=current_value,
                calibrated_data=current_value,
                status_class="normal",
            )
        )
        current_value -= delta_per_reading
        current_time += timedelta(seconds=interval_seconds)

    return readings


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.django_db(transaction=True)
class TestPeeBotProcessorIntegration:
    """Integration tests for the full PeeBot processor flow."""

    def test_full_flow_burst_detected(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Sustained burst pattern triggers event detection and Bluesky post."""
        # Arrange: Create realistic burst readings (45 seconds, ~2.25% increase)
        readings = create_burst_readings(
            upa_channel,
            burst_duration_seconds=45,
            baseline=Decimal("25.0"),
            delta_per_reading=Decimal("0.15"),
        )
        assert len(readings) > 0, "Test setup: readings should be created"

        # Act: Run the processor task
        result = run_peebot_processor()

        # Assert: Event detected
        assert result["event_detected"] is True, "Burst should trigger event detection"
        assert result["error"] is None, f"No error expected, got: {result.get('error')}"

        # Assert: DetectedEvent created with correct fields
        events = DetectedEvent.objects.filter(event_type="urination")
        assert events.count() == 1, "Exactly one event should be created"

        event = events.first()
        assert event is not None
        assert event.channel_id == "NODE3000004"
        assert Decimal("0.0") <= event.confidence <= Decimal("1.0")
        assert event.detected_at is not None
        assert event.metadata is not None

        # Assert: External services called
        mock_external_services["joke_generator"].generate.assert_called_once()
        mock_external_services["bluesky_client"].post.assert_called_once()

        # Assert: State updated
        processor_state.refresh_from_db()
        assert processor_state.last_processed_timestamp is not None
        assert processor_state.last_run_at is not None

    def test_full_flow_glitch_rejected(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Glitch pattern (spike + immediate revert) does NOT trigger event."""
        # Arrange: Create glitch readings
        readings = create_glitch_readings(
            upa_channel,
            baseline=Decimal("25.0"),
            spike_value=Decimal("32.0"),  # Significant spike
        )
        assert len(readings) > 0, "Test setup: readings should be created"

        # Act
        result = run_peebot_processor()

        # Assert: No event detected
        assert result["event_detected"] is False, "Glitch should NOT trigger event"
        assert DetectedEvent.objects.count() == 0, "No events should be created"

        # Assert: External services NOT called
        mock_external_services["joke_generator"].generate.assert_not_called()
        mock_external_services["bluesky_client"].post.assert_not_called()

    def test_full_flow_flat_no_event(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Flat readings (no trend) do NOT trigger event."""
        # Arrange: Create flat readings
        readings = create_flat_readings(
            upa_channel,
            value=Decimal("25.0"),
            count=30,
        )
        assert len(readings) > 0, "Test setup: readings should be created"

        # Act
        result = run_peebot_processor()

        # Assert: No event
        assert result["event_detected"] is False
        assert DetectedEvent.objects.count() == 0

    def test_full_flow_decreasing_no_event(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Decreasing readings (UPA processing) do NOT trigger event."""
        # Arrange
        readings = create_decreasing_readings(
            upa_channel,
            start_value=Decimal("30.0"),
            delta_per_reading=Decimal("0.1"),
            count=30,
        )
        assert len(readings) > 0

        # Act
        result = run_peebot_processor()

        # Assert
        assert result["event_detected"] is False
        assert DetectedEvent.objects.count() == 0

    def test_state_persistence_across_runs(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Processor state persists correctly across multiple runs."""
        # Run 1: Create flat readings, no event
        create_flat_readings(upa_channel, count=10, start_offset_seconds=180)
        result1 = run_peebot_processor()
        assert result1["event_detected"] is False

        processor_state.refresh_from_db()
        first_run_at = processor_state.last_run_at
        assert first_run_at is not None

        # Clear old readings and reset cursor to simulate fresh window
        TelemetryReading.objects.all().delete()
        processor_state.last_processed_timestamp = None
        processor_state.save()

        # Run 2: Create burst readings, event detected
        create_burst_readings(
            upa_channel,
            burst_duration_seconds=45,
            start_offset_seconds=120,
        )

        result2 = run_peebot_processor()
        assert result2["event_detected"] is True

        processor_state.refresh_from_db()
        second_run_at = processor_state.last_run_at
        second_processed_at = processor_state.last_processed_timestamp

        # Assert: State updated
        assert second_run_at is not None
        assert second_run_at > first_run_at
        assert second_processed_at is not None

    def test_burst_too_short_no_event(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Burst shorter than 30 seconds does NOT trigger event."""
        # Arrange: Create short burst (only 15 seconds)
        readings = create_burst_readings(
            upa_channel,
            burst_duration_seconds=15,  # Too short
            baseline=Decimal("25.0"),
            delta_per_reading=Decimal("0.2"),
        )
        assert len(readings) > 0

        # Act
        result = run_peebot_processor()

        # Assert: No event (burst too short)
        assert result["event_detected"] is False
        assert DetectedEvent.objects.count() == 0

    def test_insufficient_data_no_event(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Insufficient readings do NOT trigger event."""
        # Arrange: Only 2 readings
        now = timezone.now()
        baker.make(
            TelemetryReading,
            channel=upa_channel,
            timestamp=now - timedelta(seconds=10),
            value=Decimal("25.0"),
            calibrated_data=Decimal("25.0"),
        )
        baker.make(
            TelemetryReading,
            channel=upa_channel,
            timestamp=now - timedelta(seconds=5),
            value=Decimal("26.0"),
            calibrated_data=Decimal("26.0"),
        )

        # Act
        result = run_peebot_processor()

        # Assert
        assert result["event_detected"] is False
        assert DetectedEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
class TestSocialPostCooldownIntegration:
    """Integration tests for social post cooldown enforcement."""

    def test_cooldown_prevents_duplicate_posts(
        self,
        upa_channel: TelemetryChannel,
        processor_state: ProcessorState,
        mock_external_services: dict[str, MagicMock],
    ) -> None:
        """Second event within 30 minutes should NOT trigger Bluesky post."""
        # Arrange: Create burst and run first time
        create_burst_readings(upa_channel, burst_duration_seconds=45)

        result1 = run_peebot_processor()
        assert result1["event_detected"] is True
        assert result1["post_published"] is True

        # Simulate cooldown active for second run
        mock_external_services["bluesky_client"].check_cooldown.return_value = (
            False,
            timedelta(minutes=20),
        )

        # Create another burst pattern (new readings)
        TelemetryReading.objects.all().delete()  # Clear old readings
        create_burst_readings(
            upa_channel,
            burst_duration_seconds=45,
            start_offset_seconds=60,
        )

        # Reset processor state to detect new event
        processor_state.last_processed_timestamp = None
        processor_state.save()

        # Act: Run second time
        result2 = run_peebot_processor()

        # Assert: Event detected but no tweet (cooldown)
        assert result2["event_detected"] is True
        assert result2["post_published"] is False

        # Assert: Two events exist, but Bluesky only called once
        assert DetectedEvent.objects.count() == 2
        assert mock_external_services["bluesky_client"].post.call_count == 1
