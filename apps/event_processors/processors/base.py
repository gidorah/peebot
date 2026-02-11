"""Base processor infrastructure for event detection analytics.

This module defines the abstract BaseProcessor class that all event processors
must inherit from. It provides the contract for analytics modules including:
- Configuration attributes (processor_name, channel_pui, etc.)
- Abstract methods for analysis (analyze, get_confidence)
- State management helpers for persistence and resumption
- Jitter utility for load distribution
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from django.utils import timezone

if TYPE_CHECKING:
    from apps.event_processors.models import ProcessorState
    from apps.telemetry_storage.models import TelemetryReading

logger = structlog.get_logger(__name__)


class BaseProcessor(ABC):
    """Abstract base class for all event processors.

    Processors analyze telemetry data on a scheduled basis to detect
    operational events. Each processor runs independently with its own
    configuration and state management.

    Attributes:
        processor_name: Unique identifier for this processor (required)
        channel_pui: Target telemetry channel PUI to analyze (required)
        poll_interval_seconds: How often the processor runs (default: 30)
        window_minutes: Size of the sliding analysis window (default: 5)
    """

    processor_name: str
    channel_pui: str
    poll_interval_seconds: int = 30
    window_minutes: int = 5

    def __init__(self) -> None:
        """Initialize the processor and validate required attributes."""
        if not hasattr(self, "processor_name") or not self.processor_name:
            raise ValueError(f"{self.__class__.__name__} must define processor_name")
        if not hasattr(self, "channel_pui") or not self.channel_pui:
            raise ValueError(f"{self.__class__.__name__} must define channel_pui")

    async def apply_jitter(self, max_delay_seconds: int = 5) -> None:
        """Apply a random delay before execution.

        This prevents "thundering herd" database load spikes when multiple
        processors share the same schedule alignment. The delay is uniformly
        distributed between 0 and max_delay_seconds.

        Args:
            max_delay_seconds: Maximum delay in seconds (default: 5)
        """
        delay = random.uniform(0, max_delay_seconds)
        await asyncio.sleep(delay)

    @abstractmethod
    async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
        """Analyze readings to detect events.

        Implementations should analyze the provided telemetry readings
        and return DetectionResult if an event is detected, or None
        if no event is found.

        Args:
            readings: List of TelemetryReading objects to analyze

        Returns:
            DetectionResult with event metadata, or None
        """
        pass

    @abstractmethod
    def get_confidence(self, readings: list[TelemetryReading]) -> Decimal:
        """Calculate detection confidence score.

        Returns a confidence score between 0.0 and 1.0 based on the
        strength and consistency of the detected pattern.

        Args:
            readings: List of TelemetryReading objects used for detection

        Returns:
            Decimal confidence value (0.0-1.0)
        """
        pass

    async def load_state(self) -> ProcessorState:
        """Load or create processor state from database.

        Retrieves the ProcessorState record for this processor, creating
        it if it doesn't exist. The state includes the last_processed_at
        cursor for resumption support.

        Returns:
            ProcessorState instance for this processor
        """
        # Import here to avoid circular dependency during module load
        from apps.event_processors.models import ProcessorState

        state: ProcessorState
        state, created = await ProcessorState.objects.aget_or_create(  # type: ignore[attr-defined]
            processor_name=self.processor_name,
            defaults={
                "last_processed_at": None,
                "last_run_at": None,
                "state_data": None,
            },
        )
        if created:
            logger.info("processor_state_created", processor_name=self.processor_name)
        return state

    async def update_state_cursor(
        self, state: ProcessorState, processed_at: datetime | None = None
    ) -> None:
        """Update the processor state cursor after execution.

        Updates both last_processed_at (data cursor) and last_run_at
        (execution timestamp) to support resumption and failure tracking.

        Args:
            state: The ProcessorState instance to update
            processed_at: Timestamp of processed data (defaults to now)
        """
        now = timezone.now()
        state.last_run_at = now
        if processed_at:
            state.last_processed_at = processed_at

        await state.asave()
        logger.debug(
            "processor_state_updated",
            processor_name=self.processor_name,
            last_run_at=now.isoformat(),
            last_processed_at=processed_at.isoformat() if processed_at else None,
        )

    async def get_state_data(self, state: ProcessorState) -> dict[str, Any] | None:
        """Get processor-specific state data.

        Args:
            state: The ProcessorState instance

        Returns:
            Processor-specific state data dict, or None
        """
        return state.state_data

    async def set_state_data(
        self, state: ProcessorState, data: dict[str, Any] | None
    ) -> None:
        """Set processor-specific state data.

        Args:
            state: The ProcessorState instance to update
            data: Processor-specific state data to persist
        """
        state.state_data = data
        await state.asave(update_fields=["state_data"])


class DetectionResult:
    """Container for event detection results.

    Provides a standardized structure for passing detection results
    from processors to the task layer.
    """

    def __init__(
        self,
        event_type: str,
        detected_at: datetime,
        confidence: Decimal,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize detection result.

        Args:
            event_type: Type/category of the detected event
            detected_at: Timestamp when the event occurred
            confidence: Detection confidence (0.0-1.0)
            metadata: Optional processor-specific detection details

        Raises:
            ValueError: If confidence is not between 0.0 and 1.0
        """
        if not (Decimal("0.0") <= confidence <= Decimal("1.0")):
            raise ValueError("confidence must be between 0.0 and 1.0")
        self.event_type = event_type
        self.detected_at = detected_at
        self.confidence = confidence
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for model creation."""
        return {
            "event_type": self.event_type,
            "detected_at": self.detected_at,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
