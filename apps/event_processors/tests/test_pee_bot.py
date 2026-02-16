"""Tests for the PeeBotProcessor fill event detection.

Verifies burst detection logic, glitch filtering, confidence calculation,
and all edge cases defined in the requirements (FR-PROC-002, FR-PROC-003).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.event_processors.processors.pee_bot import PeeBotProcessor
from apps.telemetry_storage.models import TelemetryReading


def create_mock_reading(
    timestamp: datetime,
    value: float | Decimal,
    calibrated: float | Decimal | None = None,
) -> MagicMock:
    """Create a mock TelemetryReading with specified timestamp and value."""
    mock = MagicMock(spec=TelemetryReading)
    mock.timestamp = timestamp
    mock.value = Decimal(str(value))
    mock.calibrated_data = Decimal(str(calibrated)) if calibrated is not None else None
    return mock


class TestPeeBotProcessorConfiguration:
    """Tests for processor configuration and initialization."""

    def test_processor_configuration(self) -> None:
        """Processor has correct configuration attributes."""
        processor = PeeBotProcessor()

        assert processor.processor_name == "pee_bot"
        assert processor.channel_pui == "NODE3000005"
        assert processor.poll_interval_seconds == 30
        assert processor.window_minutes == 10

    def test_detection_thresholds(self) -> None:
        """Processor has correct detection thresholds."""
        processor = PeeBotProcessor()

        assert processor.MIN_BURST_DURATION_SECONDS == 30.0
        assert processor.MAX_BURST_DURATION_SECONDS == 120.0
        assert processor.STABILITY_CHECK_SECONDS == 15.0
        assert processor.GLITCH_REVERSION_SECONDS == 15.0
        assert processor.MIN_DELTA_THRESHOLD == Decimal("0.5")


class TestPeeBotProcessorAnalyze:
    """Tests for the analyze() method - burst detection logic."""

    @pytest.mark.asyncio
    async def test_sustained_burst_detected(self) -> None:
        """Sustained burst (30s-2min) with stable post-burst triggers event."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create readings with 45-second sustained increase (within 30s-2min range)
        readings = []
        # Pre-burst baseline (10 seconds)
        for i in range(3):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 5), 50.0)
            )

        # Rising burst (45 seconds)
        burst_start = base_time + timedelta(seconds=15)
        for i in range(10):
            readings.append(
                create_mock_reading(
                    burst_start + timedelta(seconds=i * 5),
                    50.0 + i * 2,  # Steady increase
                )
            )

        # Post-burst stability (level stays elevated)
        burst_end = burst_start + timedelta(seconds=45)
        for i in range(4):
            readings.append(
                create_mock_reading(
                    burst_end + timedelta(seconds=i * 5),
                    68.0,  # Stable elevated level
                )
            )

        result = await processor.analyze(readings)

        assert result is not None
        assert result.event_type == "urination"
        assert result.detected_at == burst_start
        assert Decimal("0.0") <= result.confidence <= Decimal("1.0")
        assert result.metadata["duration_seconds"] == 45.0
        assert result.metadata["channel_id"] == "NODE3000005"
        assert "tank_level_start" in result.metadata
        assert "tank_level_end" in result.metadata
        assert "delta" in result.metadata

    @pytest.mark.asyncio
    async def test_spike_glitch_rejected(self) -> None:
        """Spike that immediately reverts to baseline is rejected as glitch."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create readings with spike that quickly reverts
        readings = []
        # Baseline
        for i in range(3):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 5), 50.0)
            )

        # Quick spike (10 seconds - too short anyway)
        spike_start = base_time + timedelta(seconds=15)
        readings.append(create_mock_reading(spike_start, 50.0))
        readings.append(create_mock_reading(spike_start + timedelta(seconds=5), 65.0))
        readings.append(create_mock_reading(spike_start + timedelta(seconds=10), 70.0))

        # Immediate reversion (within 15 seconds)
        readings.append(create_mock_reading(spike_start + timedelta(seconds=12), 51.0))

        # Back to baseline
        for i in range(3):
            readings.append(
                create_mock_reading(spike_start + timedelta(seconds=15 + i * 5), 50.0)
            )

        result = await processor.analyze(readings)

        assert result is None

    @pytest.mark.asyncio
    async def test_flat_readings_no_event(self) -> None:
        """Flat readings (no change) result in no event detection."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create flat readings at constant level
        readings = []
        for i in range(20):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 10), 50.0)
            )

        result = await processor.analyze(readings)

        assert result is None

    @pytest.mark.asyncio
    async def test_small_delta_burst_rejected_by_stability(self) -> None:
        """Small delta bursts fail stability check due to noise ratio."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Baseline with slight noise
        for i in range(3):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 5),
                    50.0 + (i % 2) * 0.1,  # Tiny noise at baseline
                )
            )

        # Small increase burst (only 0.3 delta)
        # This creates a burst that's valid by duration but unstable
        burst_start = base_time + timedelta(seconds=15)
        for i in range(10):
            readings.append(
                create_mock_reading(
                    burst_start + timedelta(seconds=i * 5),
                    50.0 + i * 0.03,  # Very small increase (0.27 total)
                )
            )

        # Post-burst: return to baseline with noise
        burst_end = burst_start + timedelta(seconds=45)
        for i in range(4):
            readings.append(
                create_mock_reading(
                    burst_end + timedelta(seconds=i * 5),
                    50.1 if i % 2 == 0 else 50.0,  # Noise around baseline
                )
            )

        result = await processor.analyze(readings)

        # The burst passes duration but may fail stability check
        # or may not even be detected as a rising edge due to small delta
        assert result is None

    @pytest.mark.asyncio
    async def test_burst_too_short_rejected(self) -> None:
        """Burst shorter than 30 seconds is rejected."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Baseline
        for i in range(3):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 5), 50.0)
            )

        # Short burst (20 seconds only)
        burst_start = base_time + timedelta(seconds=15)
        for i in range(5):
            readings.append(
                create_mock_reading(
                    burst_start + timedelta(seconds=i * 5),
                    50.0 + i * 2,
                )
            )

        # Post-burst stability
        burst_end = burst_start + timedelta(seconds=20)
        for i in range(4):
            readings.append(
                create_mock_reading(burst_end + timedelta(seconds=i * 5), 58.0)
            )

        result = await processor.analyze(readings)

        assert result is None

    @pytest.mark.asyncio
    async def test_burst_too_long_rejected(self) -> None:
        """Burst longer than 2 minutes is rejected."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Baseline
        for i in range(3):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 5), 50.0)
            )

        # Long burst (3 minutes - too long)
        burst_start = base_time + timedelta(seconds=15)
        for i in range(37):  # 3 minutes at 5-second intervals
            readings.append(
                create_mock_reading(
                    burst_start + timedelta(seconds=i * 5),
                    50.0 + min(i * 0.5, 30.0),  # Gradual rise then plateau
                )
            )

        result = await processor.analyze(readings)

        assert result is None

    @pytest.mark.asyncio
    async def test_insufficient_data_no_event(self) -> None:
        """Less than 3 readings results in no detection."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time, 50.0),
            create_mock_reading(base_time + timedelta(seconds=10), 55.0),
        ]

        result = await processor.analyze(readings)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_readings_no_event(self) -> None:
        """Empty readings list results in no detection."""
        processor = PeeBotProcessor()

        result = await processor.analyze([])

        assert result is None

    @pytest.mark.asyncio
    async def test_post_burst_instability_rejected(self) -> None:
        """Burst followed by immediate sharp drop is rejected."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Baseline
        for i in range(3):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 5), 50.0)
            )

        # Valid burst (45 seconds)
        burst_start = base_time + timedelta(seconds=15)
        for i in range(10):
            readings.append(
                create_mock_reading(
                    burst_start + timedelta(seconds=i * 5),
                    50.0 + i * 2,
                )
            )

        # Sharp drop immediately after (not gradual processing)
        burst_end = burst_start + timedelta(seconds=45)
        readings.append(create_mock_reading(burst_end + timedelta(seconds=2), 68.0))
        readings.append(create_mock_reading(burst_end + timedelta(seconds=5), 52.0))
        readings.append(create_mock_reading(burst_end + timedelta(seconds=8), 50.0))

        result = await processor.analyze(readings)

        # Should be rejected due to post-burst instability
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_bursts_first_valid(self) -> None:
        """Multiple bursts in data - first valid one triggers detection."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # First burst - valid
        for i in range(3):
            readings.append(
                create_mock_reading(base_time + timedelta(seconds=i * 5), 50.0)
            )

        burst1_start = base_time + timedelta(seconds=15)
        for i in range(10):
            readings.append(
                create_mock_reading(
                    burst1_start + timedelta(seconds=i * 5),
                    50.0 + i * 2,
                )
            )

        burst1_end = burst1_start + timedelta(seconds=45)
        for i in range(4):
            readings.append(
                create_mock_reading(burst1_end + timedelta(seconds=i * 5), 68.0)
            )

        # Second burst - also valid but should not be detected (first wins)
        gap_start = burst1_end + timedelta(seconds=20)
        for i in range(5):
            readings.append(
                create_mock_reading(gap_start + timedelta(seconds=i * 5), 68.0)
            )

        burst2_start = gap_start + timedelta(seconds=25)
        for i in range(10):
            readings.append(
                create_mock_reading(
                    burst2_start + timedelta(seconds=i * 5),
                    68.0 + i * 1,
                )
            )

        result = await processor.analyze(readings)

        assert result is not None
        assert result.detected_at == burst1_start
        assert result.metadata["tank_level_end"] == "68.0"

    @pytest.mark.asyncio
    async def test_uses_calibrated_data_when_available(self) -> None:
        """Processor uses calibrated_data field when available."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Baseline with calibrated data
        for i in range(3):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 5),
                    value=50.0,  # raw value
                    calibrated=50.0,  # calibrated value
                )
            )

        # Burst with different calibrated values
        burst_start = base_time + timedelta(seconds=15)
        for i in range(10):
            readings.append(
                create_mock_reading(
                    burst_start + timedelta(seconds=i * 5),
                    value=50.0 + i * 1,  # raw
                    calibrated=50.0 + i * 2,  # calibrated (used)
                )
            )

        burst_end = burst_start + timedelta(seconds=45)
        for i in range(4):
            readings.append(
                create_mock_reading(
                    burst_end + timedelta(seconds=i * 5),
                    value=60.0,
                    calibrated=68.0,  # stable elevated
                )
            )

        result = await processor.analyze(readings)

        assert result is not None
        assert result.metadata["tank_level_start"] == "50.0"
        assert result.metadata["tank_level_end"] == "68.0"
        assert result.metadata["delta"] == "18.0"


class TestPeeBotProcessorConfidence:
    """Tests for the get_confidence() method."""

    def test_confidence_range_valid(self) -> None:
        """Confidence values are within 0.0-1.0 range."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create consistent trend readings
        readings = []
        for i in range(20):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 5),
                    50.0 + i * 2,  # Perfect linear increase
                )
            )

        confidence = processor.get_confidence(readings)

        assert isinstance(confidence, Decimal)
        assert Decimal("0.0") <= confidence <= Decimal("1.0")

    def test_confidence_zero_for_insufficient_data(self) -> None:
        """Confidence is 0.0 when less than 3 readings provided."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time, 50.0),
            create_mock_reading(base_time + timedelta(seconds=10), 55.0),
        ]

        confidence = processor.get_confidence(readings)

        assert confidence == Decimal("0.0")

    def test_confidence_zero_for_empty(self) -> None:
        """Confidence is 0.0 for empty readings list."""
        processor = PeeBotProcessor()

        confidence = processor.get_confidence([])

        assert confidence == Decimal("0.0")

    def test_high_confidence_for_strong_consistent_trend(self) -> None:
        """Strong, consistent linear trend yields high confidence."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Perfect linear trend with high sample density
        readings = []
        for i in range(30):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 3),  # High density
                    50.0 + i * 2,  # Perfect linear
                )
            )

        confidence = processor.get_confidence(readings)

        # Should be high (> 0.7) for perfect linear trend
        assert confidence > Decimal("0.7")

    def test_low_confidence_for_noisy_data(self) -> None:
        """Noisy, inconsistent data yields lower confidence than clean data."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Clean trend
        clean_readings = []
        for i in range(30):
            clean_readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 10),
                    50.0 + i * 1,
                )
            )

        # Noisy trend with random noise
        noisy_readings = []
        import random

        random.seed(42)  # Reproducible noise
        for i in range(30):
            noise = random.uniform(-15.0, 15.0)  # Larger random noise
            noisy_readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 10),
                    50.0 + i * 1 + noise,
                )
            )

        confidence_clean = processor.get_confidence(clean_readings)
        confidence_noisy = processor.get_confidence(noisy_readings)

        # Noisy data should have lower confidence than clean data
        assert confidence_noisy < confidence_clean

    def test_confidence_considers_sample_density(self) -> None:
        """Higher sample density increases confidence."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Low density readings (every 60 seconds = 1 per minute)
        # Time span: 9 minutes with 10 readings = 1.1 readings/minute
        low_density = []
        for i in range(10):
            low_density.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 60),
                    50.0 + i * 2,
                )
            )

        # High density readings (every 2 seconds)
        # Time span: 18 seconds with 10 readings = 33 readings/minute
        high_density = []
        for i in range(10):
            high_density.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 2),
                    50.0 + i * 2,
                )
            )

        confidence_low = processor.get_confidence(low_density)
        confidence_high = processor.get_confidence(high_density)

        # High density (33/min) should have higher confidence than low (1.1/min)
        assert confidence_high > confidence_low


class TestPeeBotProcessorEdgeCases:
    """Edge case tests for robustness."""

    @pytest.mark.asyncio
    async def test_single_reading_no_detection(self) -> None:
        """Single reading cannot trigger detection."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [create_mock_reading(base_time, 50.0)]

        result = await processor.analyze(readings)

        assert result is None

    @pytest.mark.asyncio
    async def test_unsorted_readings_handled(self) -> None:
        """Unsorted readings are sorted internally."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create readings in reverse order
        readings = []
        for i in range(10, -1, -1):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 5),
                    50.0 + (10 - i) * 2,
                )
            )

        # Should still work despite unsorted input
        result = await processor.analyze(readings)

        # Won't trigger due to stability check failure (last readings are early)
        # but should not crash
        assert result is None  # Expected due to data structure

    @pytest.mark.asyncio
    async def test_extremely_small_burst_no_detection(self) -> None:
        """Extremely small changes don't trigger detection."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Baseline with micro-fluctuations
        for i in range(5):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=i * 5),
                    50.0 + (i % 2) * 0.01,
                )
            )

        # Micro-increase that immediately reverses (glitch-like)
        # Only 0.05 delta over 30 seconds
        for i in range(7):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=25 + i * 5),
                    50.01 + i * 0.01,
                )
            )

        # Reverts immediately (glitch)
        for i in range(4):
            readings.append(
                create_mock_reading(
                    base_time + timedelta(seconds=60 + i * 5),
                    50.05 - i * 0.01,
                )
            )

        result = await processor.analyze(readings)

        # Should not detect - either too short, glitch-like, or too small
        assert result is None

    @pytest.mark.asyncio
    async def test_very_long_gap_between_readings(self) -> None:
        """Large time gaps between readings don't cause issues."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = []
        # Gap of 5 minutes
        readings.append(create_mock_reading(base_time, 50.0))
        readings.append(create_mock_reading(base_time + timedelta(minutes=5), 70.0))
        readings.append(
            create_mock_reading(base_time + timedelta(minutes=5, seconds=10), 70.0)
        )

        result = await processor.analyze(readings)

        # Gap too large, no sustained burst
        assert result is None


class TestBurstInfo:
    """Tests for the BurstInfo dataclass."""

    def test_burst_info_properties(self) -> None:
        """BurstInfo calculates properties correctly."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        from apps.event_processors.processors.pee_bot import BurstInfo

        burst = BurstInfo(
            start_time=base_time,
            end_time=base_time + timedelta(seconds=45),
            start_value=Decimal("50.0"),
            end_value=Decimal("70.0"),
            readings_count=10,
            intermediate_values=[Decimal("50.0"), Decimal("55.0"), Decimal("70.0")],
        )

        assert burst.duration_seconds == 45.0
        assert burst.delta == Decimal("20.0")
        assert burst.readings_count == 10
