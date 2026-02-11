"""BlueskyClient service - Bluesky API integration for social media posting.

This module provides the BlueskyClient class which uses the atproto SDK to post
to Bluesky about detected ISS urination events. It implements cooldown enforcement
to prevent spam.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import structlog
from atproto import Client
from atproto.exceptions import AtProtocolError
from django.conf import settings
from django.utils import timezone

from apps.event_processors.models import DetectedEvent, SocialPost

logger = structlog.get_logger(__name__)


class BlueskyClientError(Exception):
    """Base exception for BlueskyClient errors."""

    pass


class BlueskyCooldownError(BlueskyClientError):
    """Raised when attempting to post during cooldown period."""

    pass


class BlueskyClient:
    """Client for posting to Bluesky about detected events.

    Uses the atproto SDK for AT Protocol integration. Enforces a 30-minute cooldown
    between posts.

    Attributes:
        client: atproto Client instance
        cooldown_minutes: Minimum time between posts (default: 30)
    """

    DEFAULT_COOLDOWN_MINUTES = 30
    PLATFORM = "bluesky"

    def __init__(self) -> None:
        """Initialize the BlueskyClient with atproto.

        Raises:
            BlueskyClientError: If required credentials are not configured
        """
        handle = getattr(settings, "BLUESKY_HANDLE", None)
        app_password = getattr(settings, "BLUESKY_APP_PASSWORD", None)

        missing = []
        if not handle:
            missing.append("BLUESKY_HANDLE")
        if not app_password:
            missing.append("BLUESKY_APP_PASSWORD")

        if missing:
            raise BlueskyClientError(
                f"Missing required Bluesky credentials: {', '.join(missing)}"
            )

        self.client = Client()
        self._handle = handle
        self._app_password = app_password
        self._authenticated = False

        cooldown_setting = getattr(settings, "BLUESKY_COOLDOWN_MINUTES", None)
        self.cooldown_minutes = cooldown_setting or self.DEFAULT_COOLDOWN_MINUTES

    async def _ensure_authenticated(self) -> None:
        """Authenticate with Bluesky lazily on first use.

        Runs the synchronous login call in an executor to avoid blocking
        the event loop.

        Raises:
            BlueskyClientError: If authentication fails
        """
        if self._authenticated:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.login(self._handle, self._app_password),
            )
            self._authenticated = True
        except AtProtocolError as e:
            raise BlueskyClientError(f"Failed to authenticate with Bluesky: {e}") from e

    async def check_cooldown(self) -> tuple[bool, timedelta | None]:
        """Check if enough time has passed since the last post.

        Queries SocialPost records to find the most recent Bluesky post
        and determines if the cooldown period has elapsed.

        Returns:
            Tuple of (can_post: bool, remaining_cooldown: timedelta or None)
            - can_post: True if cooldown has elapsed, False otherwise
            - remaining_cooldown: Time until cooldown expires, or None if can_post
        """
        cooldown_threshold = timezone.now() - timedelta(minutes=self.cooldown_minutes)

        try:
            recent_post = await SocialPost.objects.filter(  # type: ignore[attr-defined]
                platform=self.PLATFORM,
                status=SocialPost.Status.SUCCESS,
                posted_at__gte=cooldown_threshold,
            ).afirst()

            if recent_post is None:
                return True, None

            remaining = (
                recent_post.posted_at
                + timedelta(minutes=self.cooldown_minutes)
                - timezone.now()
            )

            logger.info(
                "bluesky_cooldown_active",
                last_post_id=str(recent_post.id),
                last_posted_at=recent_post.posted_at.isoformat(),
                remaining_seconds=max(0, remaining.total_seconds()),
            )

            return False, max(timedelta(0), remaining)

        except Exception as e:
            logger.error(
                "bluesky_cooldown_check_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False, timedelta(minutes=self.cooldown_minutes)

    async def post(self, text: str, event: DetectedEvent) -> str | None:
        """Post text to Bluesky and create SocialPost record.

        Args:
            text: The text content to post
            event: The DetectedEvent that triggered this post

        Returns:
            Post URI string if successful, None otherwise

        Raises:
            BlueskyCooldownError: If attempting to post during cooldown
            BlueskyClientError: For other API errors
        """
        await self._ensure_authenticated()

        can_post, remaining = await self.check_cooldown()
        if not can_post and remaining:
            raise BlueskyCooldownError(
                f"Cannot post: cooldown active. "
                f"Wait {remaining.total_seconds() / 60:.1f} more minutes."
            )
        elif not can_post:
            raise BlueskyCooldownError("Cannot post: cooldown active.")

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.send_post(text=text),
            )

            if not response or not response.uri:
                logger.error(
                    "bluesky_post_no_response",
                    event_id=str(event.id),
                )
                await self._create_failed_post(
                    event, text, "No response from Bluesky API"
                )
                return None

            post_uri: str = response.uri

            social_post = await SocialPost.objects.acreate(  # type: ignore[attr-defined]
                event=event,
                platform=self.PLATFORM,
                external_id=post_uri,
                content=text,
                posted_at=timezone.now(),
                status=SocialPost.Status.SUCCESS,
            )

            logger.info(
                "bluesky_post_success",
                event_id=str(event.id),
                social_post_id=str(social_post.id),
                post_uri=post_uri,
                text_length=len(text),
            )

            return post_uri

        except AtProtocolError as e:
            error_msg = str(e)
            logger.error(
                "bluesky_api_error",
                event_id=str(event.id),
                error=error_msg,
                error_type=type(e).__name__,
            )
            await self._create_failed_post(event, text, f"API error: {error_msg}")
            raise BlueskyClientError(f"Bluesky API error: {e}") from e

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "bluesky_post_failed",
                event_id=str(event.id),
                error=error_msg,
                error_type=type(e).__name__,
            )
            await self._create_failed_post(event, text, error_msg)
            raise BlueskyClientError(f"Failed to post to Bluesky: {e}") from e

    async def _create_failed_post(
        self, event: DetectedEvent, text: str, error_message: str
    ) -> SocialPost:
        """Create a SocialPost record with failed status.

        Args:
            event: The DetectedEvent that triggered this post attempt
            text: The text content that was attempted to post
            error_message: Description of why the post failed

        Returns:
            The created SocialPost record with failed status
        """
        social_post: SocialPost = await SocialPost.objects.acreate(  # type: ignore[attr-defined]
            event=event,
            platform=self.PLATFORM,
            external_id="",
            content=text,
            posted_at=None,
            status=SocialPost.Status.FAILED,
            error_message=error_message,
        )

        logger.info(
            "bluesky_failed_post_recorded",
            event_id=str(event.id),
            social_post_id=str(social_post.id),
            error_message=error_message[:100],
        )

        return social_post
