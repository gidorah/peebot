"""Tests for the BaseProcessor abstract class.

Verifies abstract method enforcement, state management helpers,
and jitter utility functionality.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.event_processors.models import ProcessorState
from apps.event_processors.processors.base import (
    BaseProcessor,
    DetectionResult,
)
from apps.telemetry_storage.models import TelemetryReading


class ConcreteProcessor(BaseProcessor):
    """Concrete implementation for testing abstract base class."""

    processor_name = "test_processor"
    channel_pui = "NODE3000005"
    poll_interval_seconds = 30
    window_minutes = 5

    async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
        """Return dummy detection result."""
        if not readings:
            return None
        # Return a proper DetectionResult object instead of a dict
        return DetectionResult(
            event_type="test_event",
            detected_at=timezone.now(),
            confidence=Decimal("0.85"),
            metadata={"readings_count": len(readings)},
        )

    def get_confidence(self, readings: list[TelemetryReading]) -> Decimal:
        """Return dummy confidence score."""
        if not readings:
            return Decimal("0.0")
        return Decimal("0.85")


class MissingNameProcessor(BaseProcessor):
    """Processor missing required processor_name attribute."""

    channel_pui = "NODE3000005"

    async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
        return None

    def get_confidence(self, readings: list[TelemetryReading]) -> Decimal:
        return Decimal("0.0")


class MissingChannelProcessor(BaseProcessor):
    """Processor missing required channel_pui attribute."""

    processor_name = "test_processor"

    async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
        return None

    def get_confidence(self, readings: list[TelemetryReading]) -> Decimal:
        return Decimal("0.0")


# Test-specific processor classes for state helper tests (unique names for DB isolation)
class TestProcessorLoadStateCreatesNew(ConcreteProcessor):
    """Processor for test_load_state_creates_new."""

    processor_name = "test_load_state_creates_new"


class TestProcessorLoadStateReturnsExisting(ConcreteProcessor):
    """Processor for test_load_state_returns_existing."""

    processor_name = "test_load_state_returns_existing"


class TestProcessorUpdateStateCursor(ConcreteProcessor):
    """Processor for test_update_state_cursor_updates_timestamps."""

    processor_name = "test_update_state_cursor"


class TestProcessorUpdateStateCursorNoProcessed(ConcreteProcessor):
    """Processor for test_update_state_cursor_without_processed_at."""

    processor_name = "test_update_state_cursor_without_processed_at"


class TestProcessorGetStateData(ConcreteProcessor):
    """Processor for test_get_state_data_returns_data."""

    processor_name = "test_get_state_data_returns_data"


class TestProcessorGetStateDataNone(ConcreteProcessor):
    """Processor for test_get_state_data_returns_none_when_empty."""

    processor_name = "test_get_state_data_returns_none"


class TestProcessorSetStateData(ConcreteProcessor):
    """Processor for test_set_state_data_persists_data."""

    processor_name = "test_set_state_data_persists"


class TestProcessorSetStateDataUpdate(ConcreteProcessor):
    """Processor for test_set_state_data_updates_existing."""

    processor_name = "test_set_state_data_updates"


@pytest.mark.django_db
class TestBaseProcessorInitialization:
    """Tests for processor initialization and validation."""

    def test_valid_processor_initializes(self) -> None:
        """Processor with all required attributes initializes successfully."""
        processor = ConcreteProcessor()
        assert processor.processor_name == "test_processor"
        assert processor.channel_pui == "NODE3000005"
        assert processor.poll_interval_seconds == 30
        assert processor.window_minutes == 5

    def test_missing_processor_name_raises_error(self) -> None:
        """Processor without processor_name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            MissingNameProcessor()
        assert "processor_name" in str(exc_info.value)
        assert "MissingNameProcessor" in str(exc_info.value)

    def test_missing_channel_pui_raises_error(self) -> None:
        """Processor without channel_pui raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            MissingChannelProcessor()
        assert "channel_pui" in str(exc_info.value)
        assert "MissingChannelProcessor" in str(exc_info.value)

    def test_abstract_methods_enforced(self) -> None:
        """Cannot instantiate processor without implementing abstract methods."""
        with pytest.raises(TypeError):
            BaseProcessor()


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBaseProcessorJitter:
    """Tests for the jitter utility method."""

    @patch("asyncio.sleep")
    async def test_jitter_applies_delay(self, mock_sleep: AsyncMock) -> None:
        """Jitter calls asyncio.sleep with delay in expected range."""
        processor = ConcreteProcessor()
        await processor.apply_jitter(max_delay_seconds=5)

        assert mock_sleep.called
        delay = mock_sleep.call_args[0][0]
        assert 0 <= delay <= 5

    @patch("asyncio.sleep")
    async def test_jitter_custom_max_delay(self, mock_sleep: AsyncMock) -> None:
        """Jitter respects custom max_delay_seconds parameter."""
        processor = ConcreteProcessor()
        await processor.apply_jitter(max_delay_seconds=10)

        assert mock_sleep.called
        delay = mock_sleep.call_args[0][0]
        assert 0 <= delay <= 10

    @patch("asyncio.sleep")
    async def test_jitter_random_distribution(self, mock_sleep: AsyncMock) -> None:
        """Multiple jitter calls produce different delays."""
        processor = ConcreteProcessor()

        delays = []
        for _ in range(10):
            await processor.apply_jitter(max_delay_seconds=5)
            delays.append(mock_sleep.call_args[0][0])

        # Check that we got some variety (not all identical)
        assert len(set(delays)) > 1


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBaseProcessorStateHelpers:
    """Tests for state management helper methods."""

    async def test_load_state_creates_new(self) -> None:
        """load_state creates new ProcessorState if none exists."""
        processor = TestProcessorLoadStateCreatesNew()
        processor_name = processor.processor_name

        # Ensure state doesn't exist
        assert not await ProcessorState.objects.filter(
            processor_name=processor_name
        ).aexists()

        state = await processor.load_state()

        assert state.processor_name == processor_name
        assert state.last_processed_timestamp is None
        assert state.last_run_at is None
        assert state.state_data is None

    async def test_load_state_returns_existing(self) -> None:
        """load_state returns existing ProcessorState if present."""
        processor = TestProcessorLoadStateReturnsExisting()
        processor_name = processor.processor_name

        # Create existing state
        now = timezone.now()
        existing = await ProcessorState.objects.acreate(
            processor_name=processor_name,
            last_processed_timestamp=now,
            last_run_at=now,
            state_data={"cursor": 100},
        )

        state = await processor.load_state()

        assert state.id == existing.id
        assert state.last_processed_timestamp == now
        assert state.state_data == {"cursor": 100}

    async def test_update_state_cursor_updates_timestamps(self) -> None:
        """update_state_cursor updates both last_run_at and last_processed_timestamp."""
        processor = TestProcessorUpdateStateCursor()
        processor_name = processor.processor_name
        state = await ProcessorState.objects.acreate(processor_name=processor_name)

        processed_timestamp = timezone.now() - timedelta(minutes=1)
        await processor.update_state_cursor(state, processed_timestamp)

        # Reload from database
        await sync_to_async(state.refresh_from_db)()
        assert state.last_processed_timestamp == processed_timestamp
        assert state.last_run_at is not None
        assert state.last_run_at >= processed_timestamp

    async def test_update_state_cursor_without_processed_at(self) -> None:
        """update_state_cursor only updates last_run_at when processed_at is None."""
        processor = TestProcessorUpdateStateCursorNoProcessed()
        processor_name = processor.processor_name
        state = await ProcessorState.objects.acreate(
            processor_name=processor_name,
            last_processed_timestamp=timezone.now() - timedelta(hours=1),
        )

        await processor.update_state_cursor(state, None)

        await sync_to_async(state.refresh_from_db)()
        assert state.last_run_at is not None
        # last_processed_timestamp should remain unchanged
        assert state.last_processed_timestamp is not None

    async def test_get_state_data_returns_data(self) -> None:
        """get_state_data returns processor-specific state data."""
        processor = TestProcessorGetStateData()
        processor_name = processor.processor_name
        state = await ProcessorState.objects.acreate(
            processor_name=processor_name,
            state_data={"burst_start": "2024-01-01T00:00:00Z", "counter": 5},
        )

        data = await processor.get_state_data(state)

        assert data == {"burst_start": "2024-01-01T00:00:00Z", "counter": 5}

    async def test_get_state_data_returns_none_when_empty(self) -> None:
        """get_state_data returns None when state_data is None."""
        processor = TestProcessorGetStateDataNone()
        processor_name = processor.processor_name
        state = await ProcessorState.objects.acreate(
            processor_name=processor_name, state_data=None
        )

        data = await processor.get_state_data(state)

        assert data is None

    async def test_set_state_data_persists_data(self) -> None:
        """set_state_data persists processor-specific state data."""
        processor = TestProcessorSetStateData()
        processor_name = processor.processor_name
        state = await ProcessorState.objects.acreate(processor_name=processor_name)

        await processor.set_state_data(state, {"analysis_phase": "burst_detected"})

        await sync_to_async(state.refresh_from_db)()
        assert state.state_data == {"analysis_phase": "burst_detected"}

    async def test_set_state_data_updates_existing(self) -> None:
        """set_state_data overwrites existing state data."""
        processor = TestProcessorSetStateDataUpdate()
        processor_name = processor.processor_name
        state = await ProcessorState.objects.acreate(
            processor_name=processor_name,
            state_data={"old_key": "old_value"},
        )

        await processor.set_state_data(state, {"new_key": "new_value"})

        await sync_to_async(state.refresh_from_db)()
        assert state.state_data == {"new_key": "new_value"}


@pytest.mark.asyncio
class TestBaseProcessorAbstractMethods:
    """Tests for abstract method implementation contract."""

    async def test_analyze_returns_detection_result(self) -> None:
        """analyze returns dict with detection metadata."""
        processor = ConcreteProcessor()
        mock_reading = MagicMock(spec=TelemetryReading)

        result = await processor.analyze([mock_reading])

        assert result is not None
        assert isinstance(result, DetectionResult)
        assert result.event_type == "test_event"
        assert result.metadata["readings_count"] == 1

    async def test_analyze_returns_none_when_no_event(self) -> None:
        """analyze returns None when no event detected."""
        processor = ConcreteProcessor()

        result = await processor.analyze([])

        assert result is None

    def test_get_confidence_returns_decimal(self) -> None:
        """get_confidence returns Decimal in valid range."""
        processor = ConcreteProcessor()
        mock_reading = MagicMock(spec=TelemetryReading)

        confidence = processor.get_confidence([mock_reading])

        assert isinstance(confidence, Decimal)
        assert Decimal("0.0") <= confidence <= Decimal("1.0")

    def test_get_confidence_zero_for_empty(self) -> None:
        """get_confidence returns 0.0 for empty readings."""
        processor = ConcreteProcessor()

        confidence = processor.get_confidence([])

        assert confidence == Decimal("0.0")


class TestDetectionResult:
    """Tests for the DetectionResult container class."""

    def test_initialization_with_required_fields(self) -> None:
        """DetectionResult initializes with required fields."""
        now = timezone.now()
        result = DetectionResult(
            event_type="urination",
            detected_at=now,
            confidence=Decimal("0.85"),
        )

        assert result.event_type == "urination"
        assert result.detected_at == now
        assert result.confidence == Decimal("0.85")
        assert result.metadata == {}

    def test_initialization_with_metadata(self) -> None:
        """DetectionResult initializes with optional metadata."""
        now = timezone.now()
        result = DetectionResult(
            event_type="urination",
            detected_at=now,
            confidence=Decimal("0.90"),
            metadata={"burst_duration": 45, "delta": "10.5"},
        )

        assert result.metadata == {"burst_duration": 45, "delta": "10.5"}

    def test_to_dict_returns_expected_structure(self) -> None:
        """to_dict returns dict suitable for model creation."""
        now = timezone.now()
        result = DetectionResult(
            event_type="urination",
            detected_at=now,
            confidence=Decimal("0.75"),
            metadata={"key": "value"},
        )

        data = result.to_dict()

        assert data["event_type"] == "urination"
        assert data["detected_at"] == now
        assert data["confidence"] == Decimal("0.75")
        assert data["metadata"] == {"key": "value"}

    def test_confidence_validation_rejects_negative(self) -> None:
        """DetectionResult raises ValueError for negative confidence."""
        with pytest.raises(ValueError) as exc_info:
            DetectionResult(
                event_type="urination",
                detected_at=timezone.now(),
                confidence=Decimal("-0.1"),
            )
        assert "0.0" in str(exc_info.value)
        assert "1.0" in str(exc_info.value)

    def test_confidence_validation_rejects_over_one(self) -> None:
        """DetectionResult raises ValueError for confidence > 1.0."""
        with pytest.raises(ValueError) as exc_info:
            DetectionResult(
                event_type="urination",
                detected_at=timezone.now(),
                confidence=Decimal("1.01"),
            )
        assert "0.0" in str(exc_info.value)
        assert "1.0" in str(exc_info.value)

    def test_confidence_validation_accepts_boundary_values(self) -> None:
        """DetectionResult accepts confidence at boundaries 0.0 and 1.0."""
        now = timezone.now()
        # Should not raise
        result_min = DetectionResult(
            event_type="urination",
            detected_at=now,
            confidence=Decimal("0.0"),
        )
        result_max = DetectionResult(
            event_type="urination",
            detected_at=now,
            confidence=Decimal("1.0"),
        )
        assert result_min.confidence == Decimal("0.0")
        assert result_max.confidence == Decimal("1.0")
