"""TwitterClient service - Twitter API integration for social media posting.

This module provides the TwitterClient class which uses tweepy to post
tweets about detected ISS urination events. It implements cooldown enforcement
to prevent spam and respects Twitter API rate limits.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import structlog
from django.conf import settings
from django.utils import timezone
from tweepy import Client as TweepyClient
from tweepy.errors import TweepyException

from apps.event_processors.models import SocialPost

if TYPE_CHECKING:
    from apps.event_processors.models import DetectedEvent

logger = structlog.get_logger(__name__)


class TwitterClientError(Exception):
    """Base exception for TwitterClient errors."""

    pass


class TwitterRateLimitError(TwitterClientError):
    """Raised when Twitter API rate limit is hit."""

    pass


class TwitterCooldownError(TwitterClientError):
    """Raised when attempting to post during cooldown period."""

    pass


class TwitterClient:
    """Client for posting tweets about detected events.

    Uses tweepy for Twitter API v2 integration. Enforces a 30-minute cooldown
    between posts and respects Twitter API rate limits.

    Attributes:
        client: Tweepy Client instance
        cooldown_minutes: Minimum time between posts (default: 30)
    """

    DEFAULT_COOLDOWN_MINUTES = 30
    PLATFORM = "twitter"

    def __init__(self) -> None:
        """Initialize the TwitterClient with tweepy.

        Raises:
            TwitterClientError: If required API credentials are not configured
        """
        bearer_token = getattr(settings, "TWITTER_BEARER_TOKEN", None)
        api_key = getattr(settings, "TWITTER_API_KEY", None)
        api_secret = getattr(settings, "TWITTER_API_SECRET", None)
        access_token = getattr(settings, "TWITTER_ACCESS_TOKEN", None)
        access_secret = getattr(settings, "TWITTER_ACCESS_SECRET", None)

        # Check for required credentials
        missing = []
        if not api_key:
            missing.append("TWITTER_API_KEY")
        if not api_secret:
            missing.append("TWITTER_API_SECRET")
        if not access_token:
            missing.append("TWITTER_ACCESS_TOKEN")
        if not access_secret:
            missing.append("TWITTER_ACCESS_SECRET")

        if missing:
            raise TwitterClientError(
                f"Missing required Twitter credentials: {', '.join(missing)}"
            )

        self.client = TweepyClient(
            bearer_token=bearer_token,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
            wait_on_rate_limit=False,  # We handle rate limits manually
        )

        cooldown_setting = getattr(settings, "TWITTER_COOLDOWN_MINUTES", None)
        self.cooldown_minutes = cooldown_setting or self.DEFAULT_COOLDOWN_MINUTES

    async def check_cooldown(self) -> tuple[bool, timedelta | None]:
        """Check if enough time has passed since the last post.

        Queries SocialPost records to find the most recent Twitter post
        and determines if the cooldown period has elapsed.

        Returns:
            Tuple of (can_post: bool, remaining_cooldown: timedelta or None)
            - can_post: True if cooldown has elapsed, False otherwise
            - remaining_cooldown: Time until cooldown expires, or None if can_post
        """
        cooldown_threshold = timezone.now() - timedelta(minutes=self.cooldown_minutes)

        try:
            # Get most recent Twitter post
            recent_post = await SocialPost.objects.filter(
                platform=self.PLATFORM,
                posted_at__gte=cooldown_threshold,
            ).afirst()

            if recent_post is None:
                # No recent posts, cooldown has elapsed
                return True, None

            # Calculate remaining cooldown
            remaining = (
                recent_post.posted_at
                + timedelta(minutes=self.cooldown_minutes)
                - timezone.now()
            )

            logger.info(
                "twitter_cooldown_active",
                last_post_id=str(recent_post.id),
                last_posted_at=recent_post.posted_at.isoformat(),
                remaining_seconds=max(0, remaining.total_seconds()),
            )

            return False, max(timedelta(0), remaining)

        except Exception as e:
            logger.error(
                "twitter_cooldown_check_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Conservative approach: assume cooldown is active if check fails
            return False, timedelta(minutes=self.cooldown_minutes)

    async def post(self, text: str, event: DetectedEvent) -> str | None:
        """Post text to Twitter and create SocialPost record.

        Args:
            text: The text content to post
            event: The DetectedEvent that triggered this post

        Returns:
            Tweet ID string if successful, None otherwise

        Raises:
            TwitterCooldownError: If attempting to post during cooldown
            TwitterRateLimitError: If Twitter API rate limit is hit
            TwitterClientError: For other API errors
        """
        # Check cooldown first
        can_post, remaining = await self.check_cooldown()
        if not can_post and remaining:
            raise TwitterCooldownError(
                f"Cannot post: cooldown active. "
                f"Wait {remaining.total_seconds() / 60:.1f} more minutes."
            )
        elif not can_post:
            # Should not happen based on check_cooldown logic but for type safety
            raise TwitterCooldownError("Cannot post: cooldown active.")

        try:
            # Post to Twitter using synchronous tweepy in executor
            import asyncio

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,  # Default executor
                lambda: self.client.create_tweet(text=text),
            )

            if not response or not response.data:
                logger.error(
                    "twitter_post_no_response",
                    event_id=str(event.id),
                )
                return None

            tweet_id = str(response.data["id"])

            # Create SocialPost record
            social_post = await SocialPost.objects.acreate(
                event=event,
                platform=self.PLATFORM,
                external_id=tweet_id,
                content=text,
                posted_at=timezone.now(),
            )

            logger.info(
                "twitter_post_success",
                event_id=str(event.id),
                social_post_id=str(social_post.id),
                tweet_id=tweet_id,
                text_length=len(text),
            )

            return tweet_id

        except TweepyException as e:
            # Handle tweepy-specific errors
            error_code = getattr(e, "response", None)
            if error_code and error_code.status_code == 429:
                logger.error(
                    "twitter_rate_limit_hit",
                    event_id=str(event.id),
                    error=str(e),
                )
                raise TwitterRateLimitError(f"Twitter rate limit exceeded: {e}") from e

            logger.error(
                "twitter_api_error",
                event_id=str(event.id),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TwitterClientError(f"Twitter API error: {e}") from e

        except Exception as e:
            logger.error(
                "twitter_post_failed",
                event_id=str(event.id),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise TwitterClientError(f"Failed to post tweet: {e}") from e
