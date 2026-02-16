"""PeeBot Processor - UPA tank fill (urination) event detection.

This module implements :class:`~apps.event_processors.processors.pee_bot.PeeBotProcessor`.
It detects UPA tank fill events using integer-percentage telemetry from
``NODE3000005`` (WSTA tank quantity %).

Detection approach (data-driven):
- Slide a 30-second window over chronologically sorted readings.
- Compute net change across the window and require a minimum net rise (>= +2%).
- Validate the level stays elevated in the post-fill stability window (allowing
    normal ±1% jitter).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import structlog

from apps.event_processors.processors.base import BaseProcessor, DetectionResult
from apps.telemetry_storage.models import TelemetryReading

logger = structlog.get_logger(__name__)


@dataclass
class FillEvent:
    """A detected tank fill event based on net change over a time window."""

    window_start_time: datetime
    window_end_time: datetime
    start_value: Decimal
    end_value: Decimal
    peak_value: Decimal
    net_delta: Decimal
    readings_in_window: int

    @property
    def duration_seconds(self) -> float:
        return (self.window_end_time - self.window_start_time).total_seconds()


class PeeBotProcessor(BaseProcessor):
    """Processor for detecting UPA (Urine Processing Assembly) fill events.

    Monitors the UPA Tank Level channel (NODE3000005) to detect sustained
    increases in tank level that indicate urination/fill events. Uses burst
    detection with glitch filtering to avoid false positives from sensor noise.

    Configuration (per design.md section 4.4):
    - Channel: NODE3000005 (UPA Tank Level sensor)
    - Poll interval: 30 seconds
    - Observation window: 10 minutes (for context and post-burst validation)
    - Min burst duration: 10 seconds (minimum sustained increase)
    - Max burst duration: 30 seconds (expected upper bound for urination)
    - Stability check window: 60 seconds (post-burst validation period)
    """

    processor_name = "pee_bot"
    channel_pui = "NODE3000005"
    poll_interval_seconds = 30
    window_minutes = 10

    # Detection thresholds (from design.md)
    DETECTION_WINDOW_SECONDS = 30.0
    NET_DELTA_THRESHOLD = Decimal("2")
    STABILITY_WINDOW_SECONDS = 60.0
    STABILITY_TOLERANCE = Decimal("1")

    MIN_BURST_DURATION_SECONDS = 10.0
    MAX_BURST_DURATION_SECONDS = 30.0
    STABILITY_CHECK_SECONDS = 60.0
    GLITCH_REVERSION_SECONDS = 15.0
    MIN_DELTA_THRESHOLD = Decimal("2")

    def _detect_fill_event(self, readings: list[TelemetryReading]) -> FillEvent | None:
        """Detect a fill event using net-change-over-window.

        Notes:
        - Expects readings to be chronologically sorted.
        - Uses the raw `TelemetryReading.value` field (integer-like % values).
        - Returns the earliest qualifying event.

        Returns:
            FillEvent if a candidate window meets the threshold, else None.
        """
        if len(readings) < 2:
            return None

        window_seconds = self.DETECTION_WINDOW_SECONDS
        net_delta_threshold = self.NET_DELTA_THRESHOLD

        end_idx = 0

        for start_idx, start_reading in enumerate(readings):
            if end_idx < start_idx:
                end_idx = start_idx

            window_end_time = start_reading.timestamp + timedelta(
                seconds=window_seconds
            )

            while (
                end_idx + 1 < len(readings)
                and readings[end_idx + 1].timestamp <= window_end_time
            ):
                end_idx += 1

            if end_idx <= start_idx:
                continue

            start_val = readings[start_idx].value
            end_val = readings[end_idx].value
            net_delta = end_val - start_val

            if net_delta < net_delta_threshold:
                continue

            window_slice = readings[start_idx : end_idx + 1]
            peak_val = max(r.value for r in window_slice)

            return FillEvent(
                window_start_time=window_slice[0].timestamp,
                window_end_time=window_slice[-1].timestamp,
                start_value=start_val,
                end_value=end_val,
                peak_value=peak_val,
                net_delta=net_delta,
                readings_in_window=len(window_slice),
            )

        return None

    def _check_stability(
        self, fill_event: FillEvent, readings: list[TelemetryReading]
    ) -> bool:
        """Validate post-fill stability.

        After a true fill event, the tank level should remain elevated.
        This check allows normal ±1% jitter by enforcing a floor:
        all readings in the stability window must be >= (end_value - tolerance).

        Notes:
        - Expects readings to be chronologically sorted.
        - Uses the raw `TelemetryReading.value` field (integer-like % values).
        """
        stability_end_time = fill_event.window_end_time + timedelta(
            seconds=self.STABILITY_WINDOW_SECONDS
        )
        stability_readings = [
            r
            for r in readings
            if fill_event.window_end_time < r.timestamp <= stability_end_time
        ]

        if len(stability_readings) < 1:
            return True

        floor = fill_event.end_value - self.STABILITY_TOLERANCE
        return all(r.value >= floor for r in stability_readings)

    async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
        """Analyze readings to detect a fill event.

        Orchestration for the net-change-over-window detector:
        1. Sort readings chronologically
        2. Detect the earliest fill event candidate via `_detect_fill_event`
        3. Run a post-fill stability check
        4. Return a `DetectionResult` with event metadata
        """
        if len(readings) < 3:
            return None

        sorted_readings = sorted(readings, key=lambda r: r.timestamp)

        fill_event = self._detect_fill_event(sorted_readings)

        if fill_event is None:
            logger.debug("no_fill_event_detected", readings_count=len(readings))
            return None

        log = logger.bind(
            window_start=fill_event.window_start_time.isoformat(),
            window_end=fill_event.window_end_time.isoformat(),
            net_delta=str(fill_event.net_delta),
            duration=fill_event.duration_seconds,
        )

        if not self._check_stability(fill_event, sorted_readings):
            log.info("rejected_as_unstable_post_fill")
            return None

        confidence = self.get_confidence(sorted_readings, fill_event)
        log.info("fill_event_detected", confidence=str(confidence))

        return DetectionResult(
            event_type="urination",
            detected_at=fill_event.window_start_time,
            confidence=confidence,
            metadata={
                "window_start": fill_event.window_start_time.isoformat(),
                "window_end": fill_event.window_end_time.isoformat(),
                "duration_seconds": fill_event.duration_seconds,
                "tank_level_start": str(fill_event.start_value),
                "tank_level_end": str(fill_event.end_value),
                "peak_value": str(fill_event.peak_value),
                "net_delta": str(fill_event.net_delta),
                "readings_in_window": fill_event.readings_in_window,
                "channel_id": self.channel_pui,
            },
        )

    def get_confidence(
        self,
        readings: list[TelemetryReading],
        fill_event: FillEvent | None = None,
    ) -> Decimal:
        """Calculate detection confidence for integer-percentage tank readings.

        This confidence model is intentionally simple and data-driven:
        - Delta magnitude: larger net rise => higher confidence
        - Stability confirmations: more post-fill readings holding elevation => higher
        - Density: more readings inside the detection window => higher
        """
        if len(readings) < 3:
            return Decimal("0.0")

        sorted_readings = sorted(readings, key=lambda r: r.timestamp)

        if fill_event is None:
            fill_event = self._detect_fill_event(sorted_readings)

        if fill_event is None:
            return Decimal("0.0")

        stability_end_time = fill_event.window_end_time + timedelta(
            seconds=self.STABILITY_WINDOW_SECONDS
        )
        floor = fill_event.end_value - self.STABILITY_TOLERANCE
        stability_readings_count = sum(
            1
            for r in sorted_readings
            if fill_event.window_end_time < r.timestamp <= stability_end_time
            and r.value >= floor
        )

        delta_score = min(float(fill_event.net_delta) / 4.0, 1.0)
        stability_score = min(stability_readings_count / 5.0, 1.0)
        density_score = min(fill_event.readings_in_window / 6.0, 1.0)

        raw = delta_score * 0.4 + stability_score * 0.3 + density_score * 0.3
        raw = max(0.0, min(1.0, raw))
        return Decimal(str(round(raw, 2)))

    def _calculate_r_squared(self, x: list[float], y: list[float]) -> float:
        """Calculate R² (coefficient of determination) for linear fit.

        Args:
            x: Independent variable values (timestamps)
            y: Dependent variable values (tank levels)

        Returns:
            R² value between 0.0 and 1.0
        """
        n = len(x)
        if n < 2:
            return 0.0

        # Calculate means
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        # Calculate slope (m) and intercept (b) for y = mx + b
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        slope = numerator / denominator
        intercept = mean_y - slope * mean_x

        # Calculate predicted values
        y_pred = [slope * xi + intercept for xi in x]

        # Calculate R²
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - mean_y) ** 2 for i in range(n))

        if ss_tot == 0:
            return 1.0 if ss_res == 0 else 0.0

        r_squared = 1 - (ss_res / ss_tot)
        return max(0.0, min(1.0, r_squared))

    def _calculate_snr(self, values: list[float]) -> float:
        """Calculate signal-to-noise ratio.

        Uses the ratio of signal range to standard deviation.

        Args:
            values: List of tank level values

        Returns:
            Normalized SNR value between 0.0 and 1.0
        """
        if len(values) < 2:
            return 0.0

        mean_val = sum(values) / len(values)

        # Calculate standard deviation
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        std_dev = variance**0.5

        # Calculate signal range
        signal_range = max(values) - min(values)

        if std_dev == 0:
            return 1.0 if signal_range > 0 else 0.0

        # SNR = signal_range / std_dev
        snr = signal_range / std_dev

        # Normalize: assume SNR > 10 is excellent (1.0)
        normalized_snr = min(snr / 10.0, 1.0)

        return float(max(0.0, normalized_snr))
