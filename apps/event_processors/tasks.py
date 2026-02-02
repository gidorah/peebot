"""Celery tasks for event processors.

This module defines Celery periodic tasks that orchestrate the polling-based
analytics framework. Each task instantiates a processor, queries telemetry
data, runs analysis, and triggers actions on event detection.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import structlog
from asgiref.sync import async_to_sync
from celery import shared_task  # type: ignore[import-untyped]
from django.db import OperationalError
from django.utils import timezone

if TYPE_CHECKING:
    from apps.event_processors.models import DetectedEvent, ProcessorState
    from apps.event_processors.processors.base import BaseProcessor, DetectionResult
    from apps.telemetry_storage.models import TelemetryReading

logger = structlog.get_logger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 3},
    acks_late=True,
)
def run_peebot_processor(self: Any) -> dict[str, Any]:
    """Run the PeeBot processor to detect UPA tank fill events.

    This task is triggered by Celery Beat every 30 seconds. It:
    1. Applies random jitter (0-5s) to prevent thundering herd
    2. Loads processor state from database
    3. Queries TelemetryReading for NODE3000004 channel
    4. Runs burst detection analysis
    5. Creates DetectedEvent if event found
    6. Generates joke and posts to Twitter (with cooldown check)
    7. Updates processor state cursor

    Returns:
        Dict with execution summary including event detection status
    """
    return async_to_sync(_run_peebot_processor_async)()


async def _run_peebot_processor_async() -> dict[str, Any]:
    """Async implementation of the PeeBot processor task."""
    from apps.event_processors.processors.pee_bot import PeeBotProcessor

    processor = PeeBotProcessor()
    log = logger.bind(
        processor_name=processor.processor_name,
        channel_id=processor.channel_pui,
    )

    result = {
        "processor": processor.processor_name,
        "event_detected": False,
        "tweet_posted": False,
        "error": None,
    }

    state = None
    try:
        # Step 1: Apply jitter to prevent thundering herd
        log.debug("applying_jitter")
        await processor.apply_jitter()

        # Step 2: Load processor state
        log.debug("loading_processor_state")
        state = await processor.load_state()
        log.info(
            "processor_state_loaded",
            last_processed_at=state.last_processed_at.isoformat()
            if state.last_processed_at
            else None,
            last_run_at=state.last_run_at.isoformat() if state.last_run_at else None,
        )

        # Step 3: Query telemetry readings
        readings = await _query_readings(processor, state)
        log.info("readings_queried", count=len(readings))

        if not readings:
            log.info("no_readings_to_process")
            await processor.update_state_cursor(state)
            return result

        # Step 4: Run analysis
        log.debug("running_analysis")
        detection = await processor.analyze(readings)

        if detection is None:
            log.info("no_event_detected")
            # Update cursor to latest reading timestamp
            latest_timestamp = max(r.timestamp for r in readings)
            await processor.update_state_cursor(state, processed_at=latest_timestamp)
            return result

        # Step 5: Event detected - create DetectedEvent
        log.info(
            "event_detected",
            event_type=detection.event_type,
            confidence=str(detection.confidence),
            detected_at=detection.detected_at.isoformat(),
        )
        result["event_detected"] = True

        event = await _create_detected_event(processor, detection)
        log = log.bind(event_id=str(event.id), event_type=event.event_type)
        log.info("detected_event_created")

        # Step 6: Try to post to Twitter (with cooldown and joke generation)
        tweet_posted = await _try_post_to_twitter(event, log)
        result["tweet_posted"] = tweet_posted

        # Step 7: Update processor state cursor
        await processor.update_state_cursor(state, processed_at=detection.detected_at)
        log.info("processor_state_updated")

        return result

    except OperationalError:
        # Re-raise DB errors for Celery retry mechanism
        log.error("database_error", exc_info=True)
        raise

    except Exception as e:
        # Log and continue - don't let failures block future runs
        log.error(
            "processor_execution_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        result["error"] = str(e)

        # Always update last_run_at to prevent stuck state
        if state is not None:
            try:
                state.last_run_at = timezone.now()
                await state.asave(update_fields=["last_run_at"])
            except Exception:
                log.error("failed_to_update_last_run_at", exc_info=True)

        return result


async def _query_readings(
    processor: BaseProcessor, state: ProcessorState
) -> list[TelemetryReading]:
    """Query TelemetryReading for the processor's channel.

    Fetches readings from the last window_minutes, starting from
    last_processed_at if available.

    Args:
        processor: The processor instance with channel_pui and window_minutes
        state: ProcessorState with last_processed_at cursor

    Returns:
        List of TelemetryReading objects ordered by timestamp
    """
    from apps.telemetry_storage.models import TelemetryReading

    # Calculate time window
    now = timezone.now()
    window_start = now - timedelta(minutes=processor.window_minutes)

    # Use last_processed_at as cursor if available and more recent
    if state.last_processed_at and state.last_processed_at > window_start:
        # Query from last processed point, but include some overlap for context
        query_start = state.last_processed_at - timedelta(seconds=30)
    else:
        query_start = window_start

    # Query readings for the channel
    readings: list[TelemetryReading] = (
        await TelemetryReading.objects.filter(  # type: ignore[attr-defined]
            channel__public_pui=processor.channel_pui,
            timestamp__gte=query_start,
            timestamp__lte=now,
        )
        .order_by("timestamp")
        .aiterator_to_list()
    )

    return readings


async def _create_detected_event(
    processor: BaseProcessor, detection: DetectionResult
) -> DetectedEvent:
    """Create a DetectedEvent record from detection result.

    Args:
        processor: The processor that detected the event
        detection: DetectionResult with event details

    Returns:
        Created DetectedEvent instance
    """
    from apps.event_processors.models import DetectedEvent

    event: DetectedEvent = await DetectedEvent.objects.acreate(  # type: ignore[attr-defined]
        event_type=detection.event_type,
        channel_id=processor.channel_pui,
        detected_at=detection.detected_at,
        confidence=detection.confidence,
        metadata=detection.metadata,
    )
    return event


async def _try_post_to_twitter(event: DetectedEvent, log: Any) -> bool:
    """Attempt to generate a joke and post to Twitter.

    Handles all errors gracefully - failures here should not affect
    the main processing flow.

    Args:
        event: The DetectedEvent to post about
        log: Bound structlog logger

    Returns:
        True if tweet was posted successfully, False otherwise
    """
    from apps.event_processors.services.joke_generator import (
        JokeGenerator,
        JokeGeneratorError,
    )
    from apps.event_processors.services.twitter_client import (
        TwitterClient,
        TwitterClientError,
        TwitterCooldownError,
        TwitterRateLimitError,
    )

    # Check cooldown first
    try:
        twitter = TwitterClient()
    except TwitterClientError as e:
        log.warning("twitter_client_init_failed", error=str(e))
        return False

    try:
        can_post, remaining = await twitter.check_cooldown()
        if not can_post:
            log.info(
                "twitter_cooldown_active",
                remaining_seconds=remaining.total_seconds() if remaining else 0,
            )
            return False
    except Exception as e:
        log.warning("twitter_cooldown_check_failed", error=str(e))
        return False

    # Generate joke
    try:
        joke_generator = JokeGenerator()
    except JokeGeneratorError as e:
        log.warning("joke_generator_init_failed", error=str(e))
        return False

    try:
        joke_text = await joke_generator.generate(event)
        if not joke_text:
            log.warning("joke_generation_returned_empty")
            return False
        log.info("joke_generated", text_length=len(joke_text))
    except Exception as e:
        log.warning("joke_generation_failed", error=str(e))
        return False

    # Post to Twitter
    try:
        tweet_id = await twitter.post(joke_text, event)
        if tweet_id:
            log.info("tweet_posted", tweet_id=tweet_id)
            return True
        else:
            log.warning("tweet_post_returned_none")
            return False
    except TwitterCooldownError as e:
        log.info("twitter_cooldown_blocked_post", error=str(e))
        return False
    except TwitterRateLimitError as e:
        log.warning("twitter_rate_limit_hit", error=str(e))
        return False
    except TwitterClientError as e:
        log.warning("twitter_post_failed", error=str(e))
        return False
    except Exception as e:
        log.error("twitter_post_unexpected_error", error=str(e), exc_info=True)
        return False


# Monkey-patch QuerySet to add aiterator_to_list if not present
def _patch_queryset() -> None:
    """Add aiterator_to_list method to QuerySet for async iteration."""
    from django.db.models import QuerySet

    if not hasattr(QuerySet, "aiterator_to_list"):

        async def aiterator_to_list(self: Any) -> list[Any]:
            """Convert async iterator to list."""
            result: list[Any] = []
            async for item in self:
                result.append(item)
            return result

        QuerySet.aiterator_to_list = aiterator_to_list  # type: ignore[attr-defined]


_patch_queryset()
