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


class TestPeeBotProcessorBoundaryAndDataGap:
    """Boundary conditions and data-gap edge case tests.

    Cases derived from real ISS telemetry data analysis (analysis_v3.txt) and
    algorithm inspection.
    """

    # -------------------------------------------------------------------------
    # Case 1: Partial fill capture — only the tail end is in the window
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_partial_fill_tail_only_not_detected(self) -> None:
        """Only +1% captured when fill started before observation window.

        Scenario: The real fill was 18->21, but the polling window only sees
        the last step (20->21). The net delta (+1%) is below the threshold (+2%)
        so no event should be fired.
        This models a missed-beginning scenario where the celery task woke up
        late or the ingestion had a gap at the start of the session.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            # Fill started before our window — we only see the tail step
            create_mock_reading(base_time + timedelta(seconds=0), 20),
            create_mock_reading(base_time + timedelta(seconds=5), 21),
            # Stable after — would pass stability if we got here
            create_mock_reading(base_time + timedelta(seconds=35), 21),
            create_mock_reading(base_time + timedelta(seconds=65), 21),
        ]

        result = await processor.analyze(readings)

        assert result is None, (
            "A +1% tail-only capture must not be reported as a fill event "
            "(net_delta below threshold of +2%)"
        )

    # -------------------------------------------------------------------------
    # Case 4: Fill event at the exact 30-second detection window boundary
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_fill_detected_at_exact_30s_window_boundary(self) -> None:
        """End reading at exactly start + 30.0s should still be included.

        The while-loop condition is ``readings[end_idx + 1].timestamp <=
        window_end_time``.  A reading landed at precisely 30s must be captured
        inside the window (not excluded), keeping the net delta at +2%.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=15), 20),
            # Exactly at the 30s boundary
            create_mock_reading(base_time + timedelta(seconds=30), 21),
            # Post-fill stability
            create_mock_reading(base_time + timedelta(seconds=60), 21),
            create_mock_reading(base_time + timedelta(seconds=90), 21),
        ]

        result = await processor.analyze(readings)

        assert result is not None, (
            "A reading at exactly start+30s must be inside the detection "
            "window (inclusive boundary), producing a valid fill event"
        )
        assert result.metadata["net_delta"] == "2"
        assert result.metadata["tank_level_end"] == "21"

    @pytest.mark.asyncio
    async def test_fill_not_detected_one_millisecond_past_window(self) -> None:
        """End reading at start + 30.001s falls outside the window.

        Only the reading at 15s is within the window, giving net_delta=+1%
        which is below threshold, so no detection.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=15), 20),
            # 30.001s — just outside the 30s window
            create_mock_reading(base_time + timedelta(seconds=30, milliseconds=1), 21),
            create_mock_reading(base_time + timedelta(seconds=60), 21),
        ]

        result = await processor.analyze(readings)

        # Window [0s, 30s]: reads are 19 and 20 → net_delta=1 → no event.
        # Window [15s, 45.001s]: reads 20 and 21 → net_delta=1 → no event.
        assert result is None, (
            "A +2% rise where the second step lands 1ms past the 30s window "
            "must not fire — no single window captures both endpoints"
        )

    # -------------------------------------------------------------------------
    # Case 8: Post-fill stability floor boundary (exactly end_value - tolerance)
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_stability_passes_at_exact_floor_value(self) -> None:
        """Post-fill readings at exactly end_value - STABILITY_TOLERANCE pass.

        The stability floor is ``end_value - STABILITY_TOLERANCE = 21 - 1 = 20``.
        The check is ``r.value >= floor``, so a reading at exactly 20 must pass.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            # Post-fill readings sitting at exactly the floor (21 - 1 = 20)
            create_mock_reading(base_time + timedelta(seconds=35), 20),
            create_mock_reading(base_time + timedelta(seconds=50), 20),
            create_mock_reading(base_time + timedelta(seconds=65), 20),
        ]

        result = await processor.analyze(readings)

        assert result is not None, (
            "Post-fill readings at exactly end_value - 1 must satisfy the "
            "stability floor (>= check is inclusive)"
        )
        assert result.metadata["tank_level_end"] == "21"

    @pytest.mark.asyncio
    async def test_stability_fails_one_below_floor(self) -> None:
        """Post-fill reading at end_value - tolerance - 1 breaks the floor.

        ``19 < 20`` — any reading at ``end_value - 2`` must cause the stability
        check to reject the event.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=10), 20),
            create_mock_reading(base_time + timedelta(seconds=20), 21),
            # One reading dips one step below the floor
            create_mock_reading(base_time + timedelta(seconds=35), 19),
            create_mock_reading(base_time + timedelta(seconds=50), 20),
        ]

        result = await processor.analyze(readings)

        assert result is None, (
            "A post-fill reading at end_value - 2 is below the stability floor "
            "and must reject the event"
        )

    # -------------------------------------------------------------------------
    # Case 10: Large sensor jump anomaly (sensor reset / data corruption)
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_large_sensor_jump_is_detected_as_fill_event(self) -> None:
        """A massive spike (e.g. 20% -> 80%) satisfies the threshold.

        This test documents current algorithm behavior: there is no upper-bound
        guard on net_delta, so any jump >= +2% fires.  The test is deliberately
        named to make the (potentially undesirable) behavior explicit and
        visible for future design review.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 20),
            # Anomalous single-reading jump — sensor reset or corrupted data
            create_mock_reading(base_time + timedelta(seconds=5), 80),
            # Post-fill readings stay high (stability passes)
            create_mock_reading(base_time + timedelta(seconds=35), 80),
            create_mock_reading(base_time + timedelta(seconds=55), 79),
            create_mock_reading(base_time + timedelta(seconds=75), 80),
        ]

        result = await processor.analyze(readings)

        # Documents current behavior — no upper bound check exists.
        assert result is not None, (
            "Current algorithm has no upper-bound guard on net_delta: a 60% "
            "jump passes the >= +2% check.  This test documents that behavior."
        )
        assert Decimal(result.metadata["net_delta"]) >= Decimal("2")

    @pytest.mark.asyncio
    async def test_large_sensor_jump_confidence_is_maxed(self) -> None:
        """A huge net_delta saturates the delta_score component at 1.0.

        delta_score = min(net_delta / 4.0, 1.0) — any delta >= 4 maxes out
        this component.  A 60% jump should yield maximum delta contribution.

        Confidence breakdown for this fixture:
        - delta_score  = min(60 / 4.0, 1.0) = 1.0
        - stability: fill ends at t=5s, stability window is (5s, 65s].
          Readings at 35s, 50s, 65s (3 readings in window, all >= floor 79).
          stability_score = min(3 / 5.0, 1.0) = 0.6
        - density: readings at 0s and 5s in the detection window (2 readings).
          density_score = min(2 / 6.0, 1.0) ≈ 0.333
        - raw = 1.0*0.4 + 0.6*0.3 + 0.333*0.3 ≈ 0.68 → rounds to 0.68
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 20),
            create_mock_reading(base_time + timedelta(seconds=5), 80),
            create_mock_reading(base_time + timedelta(seconds=35), 80),
            create_mock_reading(base_time + timedelta(seconds=50), 80),
            create_mock_reading(base_time + timedelta(seconds=65), 80),
            create_mock_reading(base_time + timedelta(seconds=80), 80),
            create_mock_reading(base_time + timedelta(seconds=95), 80),
        ]

        confidence = processor.get_confidence(readings)

        # delta_score is saturated at 1.0; total driven by stability+density.
        assert confidence == Decimal("0.68"), (
            "With saturated delta (60%), 3 stability readings, and 2 density "
            "readings the confidence should be exactly 0.68"
        )

    # -------------------------------------------------------------------------
    # Case 12: Net delta exactly at threshold (+2%)
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_exact_threshold_delta_is_detected(self) -> None:
        """Net delta of exactly +2% must qualify for detection.

        The check is ``net_delta < net_delta_threshold``.  Since ``2 < 2`` is
        False, a delta of exactly 2 must pass and produce a fill event.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            create_mock_reading(base_time + timedelta(seconds=15), 20),
            create_mock_reading(base_time + timedelta(seconds=29), 21),
            # Post-fill stability
            create_mock_reading(base_time + timedelta(seconds=45), 21),
            create_mock_reading(base_time + timedelta(seconds=60), 21),
        ]

        result = await processor.analyze(readings)

        assert result is not None, (
            "net_delta == NET_DELTA_THRESHOLD must pass the strict-less-than "
            "check and be reported as a fill event"
        )
        assert result.metadata["net_delta"] == "2"

    @pytest.mark.asyncio
    async def test_one_below_threshold_not_detected(self) -> None:
        """Net delta of +1% (one below threshold) must not be detected.

        Even with noise bouncing mid-window, if the net start→end is only +1%
        the event must be rejected.  This complements the exact-threshold test.
        """
        processor = PeeBotProcessor()
        base_time = datetime(2024, 1, 1, 12, 0, 0)

        readings = [
            create_mock_reading(base_time + timedelta(seconds=0), 19),
            # Brief bounce up then settle at +1
            create_mock_reading(base_time + timedelta(seconds=5), 20),
            create_mock_reading(base_time + timedelta(seconds=10), 19),
            create_mock_reading(base_time + timedelta(seconds=20), 20),
            # Post-fill stability at 20
            create_mock_reading(base_time + timedelta(seconds=40), 20),
            create_mock_reading(base_time + timedelta(seconds=60), 20),
        ]

        result = await processor.analyze(readings)

        assert result is None, (
            "net_delta of +1% is strictly below the +2% threshold and must "
            "not be detected, regardless of mid-window bounces"
        )


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
