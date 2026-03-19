"""Celery tasks for event processors.

This module defines Celery periodic tasks that orchestrate the polling-based
analytics framework. Each task instantiates a processor, queries telemetry
data, runs analysis, and triggers actions on event detection.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import structlog
from asgiref.sync import async_to_sync
from celery import shared_task
from django.conf import settings
from django.db import OperationalError, close_old_connections
from django.utils import timezone
from sentry_sdk import metrics as sentry_metrics

from apps.event_processors.models import DetectedEvent, ProcessorState, SocialPost
from apps.event_processors.processors.base import BaseProcessor, DetectionResult
from apps.event_processors.processors.pee_bot import PeeBotProcessor
from apps.event_processors.services.bluesky_client import (
    BlueskyClient,
    BlueskyClientError,
    BlueskyCooldownError,
)
from apps.event_processors.services.joke_generator import (
    JokeGenerator,
    JokeGeneratorError,
)
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
    3. Queries TelemetryReading for NODE3000005 channel
    4. Runs fill-event detection analysis
    5. Creates DetectedEvent if event found
    6. Generates joke and posts to Bluesky (with cooldown check)
    7. Updates processor state cursor

    Returns:
        Dict with execution summary including event detection status
    """
    return async_to_sync(_run_peebot_processor_async)()


async def _run_peebot_processor_async() -> dict[str, Any]:
    """Async implementation of the PeeBot processor task."""
    processor = PeeBotProcessor()
    log = logger.bind(
        processor_name=processor.processor_name,
        channel_id=processor.channel_pui,
    )

    result = {
        "processor": processor.processor_name,
        "event_detected": False,
        "post_published": False,
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
            last_processed_timestamp=state.last_processed_timestamp.isoformat()
            if state.last_processed_timestamp
            else None,
            last_run_at=state.last_run_at.isoformat() if state.last_run_at else None,
        )

        # Step 3: Query telemetry readings
        readings = await _query_readings(processor, state)
        log.info("readings_queried", count=len(readings))

        sentry_metrics.count(
            "processor.run",
            1,
            attributes={"processor": processor.processor_name},
        )
        sentry_metrics.distribution(
            "processor.readings",
            len(readings),
            attributes={"processor": processor.processor_name},
        )

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
        sentry_metrics.count(
            "processor.event_detected",
            1,
            attributes={
                "processor": processor.processor_name,
                "event_type": detection.event_type,
            },
        )

        # Step 6: Try to post to Bluesky (with cooldown and joke generation)
        post_success = await _try_post_to_bluesky(event, log)
        result["post_published"] = post_success
        if post_success:
            sentry_metrics.count(
                "processor.post_published",
                1,
                attributes={
                    "processor": processor.processor_name,
                    "event_type": event.event_type,
                },
            )

        # Step 7: Update processor state cursor (advance past processed readings)
        latest_timestamp = max(r.timestamp for r in readings)
        await processor.update_state_cursor(state, processed_at=latest_timestamp)
        log.info("processor_state_updated")

        return result

    except OperationalError:
        # Close broken/stale connections so the Celery retry gets a fresh one.
        close_old_connections()
        # Log at warning – this is a transient error that Celery will retry.
        # Logging at error level would generate a Sentry event for every
        # routine connection hiccup, creating noise before retries even run.
        log.warning("database_error_retrying", exc_info=True)
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
    last_processed_timestamp if available.

    Args:
        processor: The processor instance with channel_pui and window_minutes
        state: ProcessorState with last_processed_timestamp cursor

    Returns:
        List of TelemetryReading objects ordered by timestamp
    """
    # Calculate time window
    now = timezone.now()
    window_start = now - timedelta(minutes=processor.window_minutes)

    # Use last_processed_timestamp as cursor if available and more recent
    if state.last_processed_timestamp and state.last_processed_timestamp > window_start:
        # Query from last processed point, but include some overlap for context
        query_start = state.last_processed_timestamp - timedelta(seconds=30)
    else:
        query_start = window_start

    # Query readings for the channel
    readings: list[TelemetryReading] = [
        reading
        async for reading in TelemetryReading.objects.filter(
            channel__public_pui=processor.channel_pui,
            timestamp__gte=query_start,
            timestamp__lte=now,
        ).order_by("timestamp")
    ]

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
    event: DetectedEvent = await DetectedEvent.objects.acreate(
        event_type=detection.event_type,
        channel_id=processor.channel_pui,
        detected_at=detection.detected_at,
        confidence=detection.confidence,
        metadata=detection.metadata,
    )
    return event


async def _try_post_to_bluesky(event: DetectedEvent, log: Any) -> bool:
    """Attempt to generate a joke and post to Bluesky.

    Handles all errors gracefully - failures here should not affect
    the main processing flow.

    When SOCIAL_DRY_RUN is enabled, the Bluesky API call is skipped entirely.
    No credentials are required. A SocialPost record is still created for
    observability (status=SUCCESS, external_id="dry-run://mock").

    Args:
        event: The DetectedEvent to post about
        log: Bound structlog logger

    Returns:
        True if post was successful (or dry-run simulated), False otherwise
    """
    if getattr(settings, "SOCIAL_DRY_RUN", False):
        placeholder = (
            f"[DRY RUN] Mock post for {event.event_type} event "
            f"detected at {event.detected_at.isoformat()}"
        )
        try:
            await SocialPost.objects.acreate(
                event=event,
                platform="bluesky",
                content=placeholder,
                status=SocialPost.Status.SUCCESS,
                posted_at=timezone.now(),
                external_id="dry-run://mock",
            )
            log.info(
                "social_dry_run_post",
                platform="bluesky",
                content=placeholder,
                event_id=str(event.id),
            )
        except Exception as e:
            log.error(
                "social_dry_run_record_failed",
                error=str(e),
                event_id=str(event.id),
                social_dry_run=True,
                exc_info=True,
            )
        return True

    try:
        bluesky = BlueskyClient()
    except BlueskyClientError as e:
        log.warning("bluesky_client_init_failed", error=str(e))
        return False

    try:
        joke_generator = JokeGenerator()
    except JokeGeneratorError as e:
        log.warning("joke_generator_init_failed", error=str(e))
        return False

    try:
        can_post, remaining = await bluesky.check_cooldown()
        if not can_post:
            log.info(
                "bluesky_cooldown_active",
                remaining_seconds=remaining.total_seconds() if remaining else None,
            )
            return False
    except Exception as e:
        log.warning("bluesky_cooldown_check_failed", error=str(e))
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

    try:
        post_uri = await bluesky.post(joke_text, event)
        if post_uri:
            log.info("bluesky_posted", post_uri=post_uri)
            return True
        else:
            log.warning("bluesky_post_returned_none")
            return False
    except BlueskyCooldownError as e:
        log.info("bluesky_cooldown_blocked_post", error=str(e))
        return False
    except BlueskyClientError as e:
        log.warning("bluesky_post_failed", error=str(e))
        return False
    except Exception as e:
        log.error("bluesky_post_unexpected_error", error=str(e), exc_info=True)
        return False
