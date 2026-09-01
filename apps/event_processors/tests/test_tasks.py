"""Tests for event processor Celery tasks.

Verifies the full orchestration flow of the PeeBot processor task,
including data querying, analysis, event creation, external service
triggers, and error handling.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.db import OperationalError
from django.test import override_settings
from django.utils import timezone
from model_bakery import baker

from apps.event_processors.models import DetectedEvent, ProcessorState, SocialPost
from apps.event_processors.tasks import run_peebot_processor
from apps.telemetry_storage.models import TelemetryReading

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FILL_VALUES = [
    Decimal("19"),
    Decimal("20"),
    Decimal("21"),
    Decimal("20"),
    Decimal("21"),
    Decimal("22"),
    Decimal("22"),
    Decimal("22"),
    Decimal("22"),
    Decimal("22"),
    Decimal("22"),
]


def _make_fill_readings(channel: Any) -> list[Any]:
    """Create telemetry readings that trigger a fill-event detection."""
    now = timezone.now()
    readings = []
    for i, val in enumerate(_FILL_VALUES):
        ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
        readings.append(
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=ts,
                value=val,
                calibrated_data=None,
            )
        )
    return readings


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
        self.mock_joke_gen.__aenter__ = AsyncMock(return_value=self.mock_joke_gen)
        self.mock_joke_gen.__aexit__ = AsyncMock(return_value=None)
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
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )

        # Create readings that match the redesigned detector:
        # integer-ish % values, optional -1% bounce, net +2% within 30s.
        now = timezone.now()
        readings = []
        values = [
            Decimal("19"),
            Decimal("20"),
            Decimal("21"),
            Decimal("20"),
            Decimal("21"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
        ]
        for i in range(11):  # 30 seconds at 3s intervals
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = values[i]
            readings.append(
                baker.make(
                    TelemetryReading,
                    channel=channel,
                    timestamp=ts,
                    value=val,
                    calibrated_data=None,
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
        assert event.channel_id == "NODE3000005"
        assert event.confidence > 0

        # Verify state updated
        state.refresh_from_db()
        assert state.last_processed_timestamp is not None
        assert state.last_run_at is not None

        # Verify external calls
        self.mock_joke_gen.generate.assert_called_once()
        self.mock_joke_gen.__aexit__.assert_awaited_once()
        self.mock_bluesky.post.assert_called_once()

    def test_run_peebot_processor_no_event(self) -> None:
        """Task runs but detects no event with flat readings."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
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
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )

        # Readings showing a fill event (net +2% within 30s)
        now = timezone.now()
        values = [
            Decimal("19"),
            Decimal("20"),
            Decimal("21"),
            Decimal("20"),
            Decimal("21"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
        ]
        for i in range(11):
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = values[i]
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=ts,
                value=val,
                calibrated_data=None,
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

    def test_initial_cooldown_does_not_create_joke_generator(self) -> None:
        """A known cooldown avoids allocating an unused OpenAI client."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )
        _make_fill_readings(channel)
        self.mock_bluesky.check_cooldown.return_value = (
            False,
            timedelta(minutes=15),
        )

        result = run_peebot_processor()

        assert result["event_detected"] is True
        assert result["post_published"] is False
        self.mock_joke_gen_class.assert_not_called()
        self.mock_bluesky.post.assert_not_called()

    def test_run_peebot_processor_db_error_triggers_retry(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """OperationalError closes connections, logs a warning, and re-raises for Celery retry."""
        with caplog.at_level(logging.WARNING, logger="apps.event_processors.tasks"):
            with (
                patch(
                    "apps.event_processors.processors.base.BaseProcessor.load_state",
                    new_callable=AsyncMock,
                    side_effect=OperationalError("DB down"),
                ),
                patch(
                    "apps.event_processors.tasks.close_old_connections"
                ) as mock_close,
            ):
                with pytest.raises(OperationalError, match="DB down"):
                    run_peebot_processor()

        # Broken connections must be closed so the retry starts fresh.
        mock_close.assert_called_once()

        # Must NOT be logged at ERROR or above — that would create a Sentry event for
        # every transient connection hiccup before the Celery retry even runs.
        task_error_records = [
            r
            for r in caplog.records
            if r.name == "apps.event_processors.tasks" and r.levelno >= logging.ERROR
        ]
        assert not task_error_records, (
            "OperationalError must not be logged at ERROR level; "
            "use WARNING to avoid spurious Sentry noise"
        )

    def test_run_peebot_processor_general_exception_swallowed(self) -> None:
        """General exceptions are logged but don't crash the task execution cycle."""
        baker.make(ProcessorState, processor_name="pee_bot")

        with patch(
            "apps.event_processors.processors.pee_bot.PeeBotProcessor.analyze",
            side_effect=Exception("Unexpected failure"),
        ):
            # Create some readings to trigger analyze
            channel: Any = baker.make(
                "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
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
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )

        # Fill readings (net +2% within 30s)
        now = timezone.now()
        values = [
            Decimal("19"),
            Decimal("20"),
            Decimal("21"),
            Decimal("20"),
            Decimal("21"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
        ]
        for i in range(11):
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = values[i]
            baker.make(
                TelemetryReading,
                channel=channel,
                timestamp=ts,
                value=val,
                calibrated_data=None,
            )

        # Mock joke generation returning None
        self.mock_joke_gen.generate.return_value = None

        result = run_peebot_processor()

        assert result["event_detected"] is True
        assert result["post_published"] is False
        self.mock_joke_gen.__aexit__.assert_awaited_once()
        self.mock_bluesky.post.assert_not_called()

    def test_run_peebot_processor_closes_generator_after_generation_error(
        self,
    ) -> None:
        """Task closes the OpenAI client when joke generation raises."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )
        _make_fill_readings(channel)
        self.mock_joke_gen.generate.side_effect = RuntimeError("OpenRouter failed")

        result = run_peebot_processor()

        assert result["event_detected"] is True
        assert result["post_published"] is False
        self.mock_joke_gen.__aexit__.assert_awaited_once()
        self.mock_bluesky.post.assert_not_called()

    def test_run_peebot_processor_cursor_advances_past_burst(self) -> None:
        """Cursor is set to latest reading timestamp (not burst start) after detection."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )

        # Create fill readings (net +2% within 30s)
        now = timezone.now()
        readings = []
        values = [
            Decimal("19"),
            Decimal("20"),
            Decimal("21"),
            Decimal("20"),
            Decimal("21"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
            Decimal("22"),
        ]
        for i in range(11):
            ts = now - timedelta(seconds=60) + timedelta(seconds=i * 3)
            val = values[i]
            readings.append(
                baker.make(
                    TelemetryReading,
                    channel=channel,
                    timestamp=ts,
                    value=val,
                    calibrated_data=None,
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


@pytest.mark.django_db(transaction=True)
class TestSocialDryRun:
    """Tests for the SOCIAL_DRY_RUN mode.

    Verifies that when SOCIAL_DRY_RUN=True:
    - The full event detection pipeline runs (real DB, real processor)
    - BlueskyClient and JokeGenerator are never instantiated
    - A SocialPost record is created (status=SUCCESS, external_id="dry-run://mock")
    - No external API credentials are required
    """

    @pytest.fixture(autouse=True)
    def auto_suppress_jitter(self, request: Any) -> None:
        """Suppress jitter for all dry-run tests."""
        self.jitter_patch = patch(
            "apps.event_processors.processors.base.BaseProcessor.apply_jitter",
            new_callable=AsyncMock,
        )
        self.jitter_mock = self.jitter_patch.start()
        request.addfinalizer(self.jitter_patch.stop)

    @override_settings(SOCIAL_DRY_RUN=True)
    def test_dry_run_creates_social_post_no_api_calls(self) -> None:
        """Dry-run mode creates a SocialPost record and skips external services."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )
        _make_fill_readings(channel)

        with (
            patch("apps.event_processors.tasks.BlueskyClient") as mock_bluesky_cls,
            patch("apps.event_processors.tasks.JokeGenerator") as mock_joke_gen_cls,
        ):
            result = run_peebot_processor()

        # Task reported success
        assert result["event_detected"] is True
        assert result["post_published"] is True
        assert result["error"] is None

        # External service constructors were never called
        mock_bluesky_cls.assert_not_called()
        mock_joke_gen_cls.assert_not_called()

        # A SocialPost record exists with the dry-run sentinel values
        assert SocialPost.objects.count() == 1
        post = SocialPost.objects.get()
        assert post.status == SocialPost.Status.SUCCESS
        assert post.external_id == "dry-run://mock"
        assert post.platform == "bluesky"
        assert post.posted_at is not None
        assert "[DRY RUN]" in post.content

    @override_settings(SOCIAL_DRY_RUN=True)
    def test_dry_run_no_bluesky_credentials_required(self) -> None:
        """Dry-run mode works even when Bluesky and OpenRouter are not configured."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )
        _make_fill_readings(channel)

        # Do NOT patch BlueskyClient or JokeGenerator — they should never be reached.
        # Do NOT patch settings to add credentials.
        # The task must succeed purely from SOCIAL_DRY_RUN=True.
        with (
            override_settings(
                BLUESKY_HANDLE=None, BLUESKY_APP_PASSWORD=None, OPENROUTER_API_KEY=None
            ),
        ):
            result = run_peebot_processor()

        assert result["post_published"] is True
        assert SocialPost.objects.filter(external_id="dry-run://mock").exists()

    @override_settings(SOCIAL_DRY_RUN=False)
    def test_dry_run_off_uses_real_clients(self) -> None:
        """Sanity check: SOCIAL_DRY_RUN=False takes the normal posting path."""
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )
        _make_fill_readings(channel)

        mock_bluesky = MagicMock()
        mock_bluesky.check_cooldown = AsyncMock(return_value=(True, None))
        mock_bluesky.post = AsyncMock(
            return_value="at://did:plc:xxx/app.bsky.feed.post/456"
        )
        mock_joke_gen = MagicMock()
        mock_joke_gen.generate = AsyncMock(return_value="Real joke text")
        mock_joke_gen.__aenter__ = AsyncMock(return_value=mock_joke_gen)
        mock_joke_gen.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "apps.event_processors.tasks.BlueskyClient", return_value=mock_bluesky
            ) as mock_bluesky_cls,
            patch(
                "apps.event_processors.tasks.JokeGenerator", return_value=mock_joke_gen
            ) as mock_joke_gen_cls,
        ):
            result = run_peebot_processor()

        assert result["post_published"] is True
        mock_bluesky_cls.assert_called_once()
        mock_joke_gen_cls.assert_called_once()
        # No dry-run SocialPost created; BlueskyClient.post() was called instead
        assert not SocialPost.objects.filter(external_id="dry-run://mock").exists()

    @override_settings(SOCIAL_DRY_RUN=True)
    def test_dry_run_db_failure_is_non_fatal(self) -> None:
        """DB failure during dry-run SocialPost creation does not interrupt the flow.

        If acreate() raises (e.g. transient DB error), _try_post_to_bluesky must
        still return True so the caller updates the processor state cursor normally.
        """
        baker.make(ProcessorState, processor_name="pee_bot")
        channel: Any = baker.make(
            "telemetry_storage.TelemetryChannel", public_pui="NODE3000005"
        )
        _make_fill_readings(channel)

        with (
            patch("apps.event_processors.tasks.BlueskyClient") as mock_bluesky_cls,
            patch("apps.event_processors.tasks.JokeGenerator") as mock_joke_gen_cls,
            patch(
                "apps.event_processors.tasks.SocialPost.objects.acreate",
                side_effect=Exception("DB timeout"),
            ),
        ):
            result = run_peebot_processor()

        # Task still reports post_published=True — dry-run failure is non-fatal
        assert result["event_detected"] is True
        assert result["post_published"] is True
        assert result["error"] is None

        # External service constructors were still never called
        mock_bluesky_cls.assert_not_called()
        mock_joke_gen_cls.assert_not_called()

        # No SocialPost was persisted (acreate raised)
        assert SocialPost.objects.count() == 0
