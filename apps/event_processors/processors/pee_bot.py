"""PeeBot Processor - UPA Tank Level Event Detection.

This module implements the PeeBotProcessor which detects urination (fill) events
from the UPA Tank Level telemetry channel (NODE3000005). It uses burst detection
with glitch filtering to distinguish real fills from sensor noise.

Detection Logic:
1. Query last 5-10 minutes of readings for the UPA Tank Level channel
2. Identify rising edges (periods where level is increasing)
3. Validate burst is sustained for 30s-2min AND exceeds minimum delta
4. Filter glitches: if level reverts to baseline within 15 seconds, ignore
5. Verify post-burst stability (level stays elevated or slowly decreases)
6. Create DetectedEvent with confidence score based on trend consistency
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

import structlog

from apps.event_processors.processors.base import BaseProcessor, DetectionResult
from apps.telemetry_storage.models import TelemetryReading

logger = structlog.get_logger(__name__)


@dataclass
class BurstInfo:
    """Information about a detected burst pattern.

    Tracks the characteristics of a potential fill event burst for validation.
    """

    start_time: datetime
    end_time: datetime
    start_value: Decimal
    end_value: Decimal
    readings_count: int = 0
    intermediate_values: list[Decimal] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Calculate burst duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()

    @property
    def delta(self) -> Decimal:
        """Calculate total value change during burst."""
        return self.end_value - self.start_value


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
    - Min burst duration: 30 seconds (minimum sustained increase)
    - Max burst duration: 2 minutes (expected upper bound for urination)
    - Stability check window: 15 seconds (post-burst validation period)
    """

    processor_name = "pee_bot"
    channel_pui = "NODE3000005"
    poll_interval_seconds = 30
    window_minutes = 10

    # Detection thresholds (from design.md)
    MIN_BURST_DURATION_SECONDS = 30.0
    MAX_BURST_DURATION_SECONDS = 120.0  # 2 minutes
    STABILITY_CHECK_SECONDS = 15.0
    GLITCH_REVERSION_SECONDS = 15.0
    MIN_DELTA_THRESHOLD = Decimal("0.5")  # Minimum tank level change to qualify

    def _detect_fill_event(
        self,
        readings: list[TelemetryReading],
        *,
        window_seconds: float,
        net_delta_threshold: Decimal,
    ) -> FillEvent | None:
        """Detect a fill event using net-change-over-window.

        Notes:
        - Expects readings to be chronologically sorted.
        - Uses the raw `TelemetryReading.value` field (integer-like % values).
        - Returns the earliest qualifying event.

        Args:
            readings: Chronologically sorted TelemetryReading list.
            window_seconds: Sliding window size in seconds.
            net_delta_threshold: Minimum net rise required within the window.

        Returns:
            FillEvent if a candidate window meets the threshold, else None.
        """
        if len(readings) < 2:
            return None

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

    async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
        """Analyze readings to detect fill events.

        Implements burst detection with glitch filtering:
        1. Identifies rising edges (sustained increases)
        2. Validates burst duration is within acceptable range
        3. Filters glitches (spikes that revert quickly)
        4. Checks post-burst stability

        Args:
            readings: List of TelemetryReading objects ordered by timestamp

        Returns:
            DetectionResult if event detected, None otherwise
        """
        if len(readings) < 3:
            return None

        # Sort readings by timestamp to ensure chronological order
        sorted_readings = sorted(readings, key=lambda r: r.timestamp)

        # Detect bursts in the readings
        bursts = self._detect_bursts(sorted_readings)

        if not bursts:
            logger.debug("no_bursts_detected", readings_count=len(readings))
            return None

        for burst in bursts:
            log = logger.bind(
                burst_start=burst.start_time.isoformat(),
                burst_end=burst.end_time.isoformat(),
                delta=str(burst.delta),
                duration=burst.duration_seconds,
            )

            # Validate burst duration
            if not self._is_valid_burst_duration(burst):
                log.debug("invalid_burst_duration")
                continue

            # Check if it's a glitch (quick reversion)
            if self._is_glitch(burst, sorted_readings):
                log.info("rejected_as_glitch")
                continue

            # Check post-burst stability
            if not self._check_post_burst_stability(burst, sorted_readings):
                log.info("rejected_as_unstable_post_burst")
                continue

            # Calculate confidence based on trend strength
            confidence = self.get_confidence(sorted_readings)

            log.info("fill_event_detected", confidence=str(confidence))

            # Create detection result
            return DetectionResult(
                event_type="urination",
                detected_at=burst.start_time,
                confidence=confidence,
                metadata={
                    "burst_start": burst.start_time.isoformat(),
                    "burst_end": burst.end_time.isoformat(),
                    "duration_seconds": burst.duration_seconds,
                    "tank_level_start": str(burst.start_value),
                    "tank_level_end": str(burst.end_value),
                    "delta": str(burst.delta),
                    "readings_count": burst.readings_count,
                    "channel_id": self.channel_pui,
                },
            )

        return None

    def _detect_bursts(self, readings: list[TelemetryReading]) -> list[BurstInfo]:
        """Detect rising-edge bursts in the readings.

        Identifies periods of sustained increase in tank level.

        Args:
            readings: Chronologically sorted TelemetryReading list

        Returns:
            List of BurstInfo objects describing detected bursts
        """
        if len(readings) < 2:
            return []

        bursts = []
        current_burst: BurstInfo | None = None

        for i in range(len(readings) - 1):
            current = readings[i]
            next_reading = readings[i + 1]

            # Use calibrated_data if available, otherwise value
            current_val = current.calibrated_data or current.value
            next_val = next_reading.calibrated_data or next_reading.value

            # Check for rising edge
            if next_val > current_val:
                if current_burst is None:
                    # Start new burst
                    current_burst = BurstInfo(
                        start_time=current.timestamp,
                        end_time=next_reading.timestamp,
                        start_value=current_val,
                        end_value=next_val,
                        readings_count=2,
                        intermediate_values=[current_val, next_val],
                    )
                else:
                    # Continue existing burst
                    current_burst.end_time = next_reading.timestamp
                    current_burst.end_value = next_val
                    current_burst.readings_count += 1
                    current_burst.intermediate_values.append(next_val)
            else:
                # Not rising - end current burst if exists
                if current_burst is not None:
                    # Only add if burst has meaningful duration and delta
                    if (
                        current_burst.duration_seconds
                        >= self.MIN_BURST_DURATION_SECONDS
                        and current_burst.delta >= self.MIN_DELTA_THRESHOLD
                    ):
                        bursts.append(current_burst)
                    current_burst = None

        # Don't forget the last burst if still active
        if current_burst is not None:
            if (
                current_burst.duration_seconds >= self.MIN_BURST_DURATION_SECONDS
                and current_burst.delta >= self.MIN_DELTA_THRESHOLD
            ):
                bursts.append(current_burst)

        return bursts

    def _is_valid_burst_duration(self, burst: BurstInfo) -> bool:
        """Check if burst duration is within acceptable range.

        Args:
            burst: BurstInfo to validate

        Returns:
            True if burst duration is valid (30s-2min)
        """
        duration = burst.duration_seconds
        return (
            self.MIN_BURST_DURATION_SECONDS
            <= duration
            <= self.MAX_BURST_DURATION_SECONDS
        )

    def _is_glitch(self, burst: BurstInfo, readings: list[TelemetryReading]) -> bool:
        """Check if burst is a sensor glitch (quick reversion).

        A glitch is detected if the level returns to baseline within
        ~15 seconds after the burst ends.

        Args:
            burst: The detected burst to check
            readings: Full list of readings for context

        Returns:
            True if detected as glitch, False otherwise
        """
        # Find readings after the burst ends
        post_burst_readings = [
            r
            for r in readings
            if r.timestamp > burst.end_time
            and (r.timestamp - burst.end_time).total_seconds()
            <= self.GLITCH_REVERSION_SECONDS
        ]

        if not post_burst_readings:
            # No readings in reversion window - assume not glitch (stable)
            return False

        # Check if level reverts to near baseline
        baseline = burst.start_value
        threshold = burst.delta * Decimal("0.1")  # 10% reversion threshold

        for reading in post_burst_readings:
            val = reading.calibrated_data or reading.value
            # If level dropped back near baseline, it's a glitch
            if abs(val - baseline) < threshold:
                return True

        return False

    def _check_post_burst_stability(
        self, burst: BurstInfo, readings: list[TelemetryReading]
    ) -> bool:
        """Verify level stabilizes or slowly decreases after burst.

        After a real fill event, the tank level should remain elevated
        or slowly decrease (as UPA processes the urine). An immediate
        sharp drop suggests a sensor error.

        Args:
            burst: The detected burst to check
            readings: Full list of readings for context

        Returns:
            True if post-burst behavior is stable, False otherwise
        """
        # Find readings in stability window after burst
        stability_readings = [
            r
            for r in readings
            if r.timestamp > burst.end_time
            and (r.timestamp - burst.end_time).total_seconds()
            <= self.STABILITY_CHECK_SECONDS
        ]

        if len(stability_readings) < 2:
            # Not enough data to validate - conservatively accept
            return True

        # Check trend in stability window
        values = [r.calibrated_data or r.value for r in stability_readings]

        # Calculate slope - should be flat or slowly decreasing
        total_change = values[-1] - values[0]
        time_span = (
            stability_readings[-1].timestamp - stability_readings[0].timestamp
        ).total_seconds()

        if time_span == 0:
            return True

        # Rate of change (per minute)
        rate_per_minute = (total_change / Decimal(str(time_span))) * 60

        # Valid if: flat (-5% to +2% of burst delta per minute)
        # or slowly decreasing (negative rate, but not too steep)
        burst_delta = burst.delta
        if burst_delta == 0:
            return True

        threshold_negative = burst_delta * Decimal("-0.15")  # -15% per minute max drop
        threshold_positive = burst_delta * Decimal("0.05")  # +5% per minute max rise

        # Accept if rate is between thresholds (stable or slowly decreasing)
        return threshold_negative <= rate_per_minute <= threshold_positive

    def get_confidence(self, readings: list[TelemetryReading]) -> Decimal:
        """Calculate detection confidence based on trend strength and consistency.

        Confidence factors:
        - Trend consistency (R² of linear fit): 40% weight
        - Signal-to-noise ratio: 30% weight
        - Sample density (readings per minute): 30% weight

        Args:
            readings: List of TelemetryReading objects

        Returns:
            Decimal confidence value between 0.0 and 1.0
        """
        if len(readings) < 3:
            return Decimal("0.0")

        sorted_readings = sorted(readings, key=lambda r: r.timestamp)
        values = [float(r.calibrated_data or r.value) for r in sorted_readings]
        timestamps = [r.timestamp.timestamp() for r in sorted_readings]

        # Calculate trend consistency using linear regression R²
        r_squared = self._calculate_r_squared(timestamps, values)

        # Calculate signal-to-noise ratio
        snr = self._calculate_snr(values)

        # Calculate sample density (readings per minute)
        time_span_minutes = (timestamps[-1] - timestamps[0]) / 60.0
        if time_span_minutes > 0:
            sample_density = min(len(readings) / time_span_minutes / 2, 1.0)
        else:
            sample_density = 0.0

        # Weighted combination
        confidence = r_squared * 0.4 + snr * 0.3 + sample_density * 0.3

        # Clamp to 0.0-1.0 range
        confidence = max(0.0, min(1.0, confidence))

        return Decimal(str(round(confidence, 2)))

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
