"""Tests for the PeeBotProcessor fill event detection.

These tests validate the net-change-over-window algorithm for integer-percent
tank level readings on NODE3000005, including stability checks and confidence
scoring.
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
) -> MagicMock:
    """Create a mock TelemetryReading with specified timestamp and value."""
    mock = MagicMock(spec=TelemetryReading)
    mock.timestamp = timestamp
    mock.value = Decimal(str(value))
    return mock


class TestPeeBotProcessorConfiguration:
    """Configuration and threshold tests."""

    def test_channel_pui_is_NODE3000005(self) -> None:
        processor = PeeBotProcessor()
        assert processor.channel_pui == "NODE3000005"

    def test_detection_thresholds_match_data_analysis(self) -> None:
        processor = PeeBotProcessor()
        assert processor.DETECTION_WINDOW_SECONDS == 30.0
        assert processor.NET_DELTA_THRESHOLD == Decimal("2")
        assert processor.STABILITY_WINDOW_SECONDS == 60.0
        assert processor.STABILITY_TOLERANCE == Decimal("1")


class TestPeeBotProcessorAnalyzeHappyPath:
    """Happy-path detection tests."""

    @pytest.mark.asyncio
    async def test_clear_fill_event_detected(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=5), 20),
            create_mock_reading(base_time + timedelta(seconds=10), 21),
            create_mock_reading(base_time + timedelta(seconds=15), 22),
            create_mock_reading(base_time + timedelta(seconds=25), 22),
            create_mock_reading(base_time + timedelta(seconds=40), 22),
            create_mock_reading(base_time + timedelta(seconds=70), 22),
        ]

        result = await processor.analyze(readings)

        assert result is not None
        assert result.event_type == "urination"
        assert result.detected_at == base_time
        assert result.metadata["channel_id"] == "NODE3000005"
        assert result.metadata["net_delta"] == "3"
        assert result.metadata["tank_level_start"] == "19"
        assert result.metadata["tank_level_end"] == "22"

    @pytest.mark.asyncio
    async def test_fill_event_with_noise_bounce_detected(self) -> None:
        """Critical: mid-fill ±1% bounce should still be detected via net delta."""
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=5), 20),
            create_mock_reading(base_time + timedelta(seconds=10), 21),
            create_mock_reading(base_time + timedelta(seconds=15), 20),
            create_mock_reading(base_time + timedelta(seconds=18), 21),
            create_mock_reading(base_time + timedelta(seconds=22), 22),
            create_mock_reading(base_time + timedelta(seconds=30), 22),
            create_mock_reading(base_time + timedelta(seconds=55), 22),
        ]

        result = await processor.analyze(readings)

        assert result is not None
        assert result.event_type == "urination"
        assert result.metadata["net_delta"] in {"2", "3"}
        assert result.metadata["tank_level_end"] == "22"

    @pytest.mark.asyncio
    async def test_three_percent_fill_detected(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 27),
            create_mock_reading(base_time + timedelta(seconds=5), 28),
            create_mock_reading(base_time + timedelta(seconds=10), 29),
            create_mock_reading(base_time + timedelta(seconds=17), 30),
            create_mock_reading(base_time + timedelta(seconds=25), 30),
            create_mock_reading(base_time + timedelta(seconds=60), 30),
        ]

        result = await processor.analyze(readings)

        assert result is not None
        assert result.metadata["net_delta"] == "3"


class TestPeeBotProcessorAnalyzeNoiseRejection:
    """False-positive prevention tests."""

    @pytest.mark.asyncio
    async def test_boundary_oscillation_rejected(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 50),
            create_mock_reading(base_time + timedelta(seconds=10), 51),
            create_mock_reading(base_time + timedelta(seconds=20), 50),
            create_mock_reading(base_time + timedelta(seconds=30), 51),
            create_mock_reading(base_time + timedelta(seconds=40), 50),
            create_mock_reading(base_time + timedelta(seconds=50), 51),
        ]

        result = await processor.analyze(readings)
        assert result is None

    @pytest.mark.asyncio
    async def test_single_step_noise_rejected(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 20),
            create_mock_reading(base_time + timedelta(seconds=3), 21),
            create_mock_reading(base_time + timedelta(seconds=6), 20),
            create_mock_reading(base_time + timedelta(seconds=30), 20),
        ]

        result = await processor.analyze(readings)
        assert result is None

    @pytest.mark.asyncio
    async def test_drain_with_noise_rejected(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 22),
            create_mock_reading(base_time + timedelta(seconds=5), 21),
            create_mock_reading(base_time + timedelta(seconds=10), 22),
            create_mock_reading(base_time + timedelta(seconds=15), 21),
            create_mock_reading(base_time + timedelta(seconds=20), 20),
            create_mock_reading(base_time + timedelta(seconds=25), 19),
            create_mock_reading(base_time + timedelta(seconds=45), 19),
        ]

        result = await processor.analyze(readings)
        assert result is None


class TestPeeBotProcessorAnalyzeStability:
    """Post-fill stability validation tests."""

    @pytest.mark.asyncio
    async def test_fill_without_stability_data_accepted(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
        ]

        result = await processor.analyze(readings)
        assert result is not None

    @pytest.mark.asyncio
    async def test_fill_that_reverts_rejected(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            create_mock_reading(base_time + timedelta(seconds=25), 19),
            create_mock_reading(base_time + timedelta(seconds=40), 19),
        ]

        result = await processor.analyze(readings)
        assert result is None

    @pytest.mark.asyncio
    async def test_fill_with_slow_drain_accepted(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            create_mock_reading(base_time + timedelta(seconds=35), 21),
            create_mock_reading(base_time + timedelta(seconds=50), 20),
            create_mock_reading(base_time + timedelta(seconds=75), 20),
        ]

        result = await processor.analyze(readings)
        assert result is not None


class TestPeeBotProcessorAnalyzeEdgeCases:
    """Edge-case behavior tests."""

    @pytest.mark.asyncio
    async def test_empty_readings_no_event(self) -> None:
        processor = PeeBotProcessor()
        assert await processor.analyze([]) is None

    @pytest.mark.asyncio
    async def test_insufficient_readings_no_event(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 21),
        ]
        assert await processor.analyze(readings) is None

    @pytest.mark.asyncio
    async def test_unsorted_readings_handled(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=25), 22),
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 21),
            create_mock_reading(base_time + timedelta(seconds=5), 20),
            create_mock_reading(base_time + timedelta(seconds=40), 22),
        ]

        result = await processor.analyze(readings)
        assert result is not None
        assert result.detected_at == base_time

    @pytest.mark.asyncio
    async def test_flat_readings_no_event(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        readings = [
            create_mock_reading(base_time + timedelta(seconds=i * 10), 50)
            for i in range(10)
        ]
        assert await processor.analyze(readings) is None

    @pytest.mark.asyncio
    async def test_all_same_value_no_event(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        readings = [
            create_mock_reading(base_time + timedelta(seconds=i * 5), 33)
            for i in range(8)
        ]
        assert await processor.analyze(readings) is None


class TestPeeBotProcessorConfidence:
    """Confidence scoring tests."""

    def test_confidence_range_valid(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            create_mock_reading(base_time + timedelta(seconds=30), 21),
        ]

        confidence = processor.get_confidence(readings)
        assert isinstance(confidence, Decimal)
        assert Decimal("0.0") <= confidence <= Decimal("1.0")

    def test_higher_delta_higher_confidence(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        delta_2 = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            create_mock_reading(base_time + timedelta(seconds=30), 21),
            create_mock_reading(base_time + timedelta(seconds=40), 21),
            create_mock_reading(base_time + timedelta(seconds=50), 21),
            create_mock_reading(base_time + timedelta(seconds=60), 21),
        ]

        delta_3 = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 22),
            create_mock_reading(base_time + timedelta(seconds=30), 22),
            create_mock_reading(base_time + timedelta(seconds=40), 22),
            create_mock_reading(base_time + timedelta(seconds=50), 22),
            create_mock_reading(base_time + timedelta(seconds=60), 22),
        ]

        confidence_2 = processor.get_confidence(delta_2)
        confidence_3 = processor.get_confidence(delta_3)
        assert confidence_3 > confidence_2

    def test_more_stability_readings_higher_confidence(self) -> None:
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        low_stability = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            create_mock_reading(base_time + timedelta(seconds=30), 21),
        ]
        high_stability = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            create_mock_reading(base_time + timedelta(seconds=30), 21),
            create_mock_reading(base_time + timedelta(seconds=40), 21),
            create_mock_reading(base_time + timedelta(seconds=50), 21),
            create_mock_reading(base_time + timedelta(seconds=60), 21),
            create_mock_reading(base_time + timedelta(seconds=70), 21),
        ]

        confidence_low = processor.get_confidence(low_stability)
        confidence_high = processor.get_confidence(high_stability)
        assert confidence_high > confidence_low
