"""Tests for the TwitterClient service.

Verifies cooldown enforcement, posting functionality, error handling,
and SocialPost record creation.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from django.utils import timezone

from apps.event_processors.models import DetectedEvent, SocialPost
from apps.event_processors.services.twitter_client import (
    TwitterClient,
    TwitterClientError,
    TwitterCooldownError,
    TwitterRateLimitError,
)


class TestTwitterClientInitialization:
    """Tests for TwitterClient initialization."""

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_with_all_credentials(self, mock_settings: MagicMock) -> None:
        """TwitterClient initializes with all required credentials."""
        mock_settings.TWITTER_API_KEY = "api_key"
        mock_settings.TWITTER_API_SECRET = "api_secret"
        mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
        mock_settings.TWITTER_ACCESS_SECRET = "access_secret"
        mock_settings.TWITTER_BEARER_TOKEN = None
        mock_settings.TWITTER_COOLDOWN_MINUTES = None

        client = TwitterClient()

        assert client.client is not None
        assert client.cooldown_minutes == 30  # Default

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_with_optional_bearer_token(self, mock_settings: MagicMock) -> None:
        """TwitterClient accepts optional bearer token."""
        mock_settings.TWITTER_API_KEY = "api_key"
        mock_settings.TWITTER_API_SECRET = "api_secret"
        mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
        mock_settings.TWITTER_ACCESS_SECRET = "access_secret"
        mock_settings.TWITTER_BEARER_TOKEN = "bearer_token"
        mock_settings.TWITTER_COOLDOWN_MINUTES = None

        client = TwitterClient()

        assert client.client is not None

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_with_custom_cooldown(self, mock_settings: MagicMock) -> None:
        """TwitterClient uses custom cooldown when provided."""
        mock_settings.TWITTER_API_KEY = "api_key"
        mock_settings.TWITTER_API_SECRET = "api_secret"
        mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
        mock_settings.TWITTER_ACCESS_SECRET = "access_secret"
        mock_settings.TWITTER_BEARER_TOKEN = None
        mock_settings.TWITTER_COOLDOWN_MINUTES = 60

        client = TwitterClient()

        assert client.cooldown_minutes == 60

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_missing_api_key_raises_error(self, mock_settings: MagicMock) -> None:
        """TwitterClient raises error when API key missing."""
        mock_settings.TWITTER_API_KEY = None
        mock_settings.TWITTER_API_SECRET = "api_secret"
        mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
        mock_settings.TWITTER_ACCESS_SECRET = "access_secret"

        with pytest.raises(TwitterClientError) as exc_info:
            TwitterClient()

        assert "TWITTER_API_KEY" in str(exc_info.value)

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_missing_api_secret_raises_error(
        self, mock_settings: MagicMock
    ) -> None:
        """TwitterClient raises error when API secret missing."""
        mock_settings.TWITTER_API_KEY = "api_key"
        mock_settings.TWITTER_API_SECRET = None
        mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
        mock_settings.TWITTER_ACCESS_SECRET = "access_secret"

        with pytest.raises(TwitterClientError) as exc_info:
            TwitterClient()

        assert "TWITTER_API_SECRET" in str(exc_info.value)

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_missing_access_token_raises_error(
        self, mock_settings: MagicMock
    ) -> None:
        """TwitterClient raises error when access token missing."""
        mock_settings.TWITTER_API_KEY = "api_key"
        mock_settings.TWITTER_API_SECRET = "api_secret"
        mock_settings.TWITTER_ACCESS_TOKEN = None
        mock_settings.TWITTER_ACCESS_SECRET = "access_secret"

        with pytest.raises(TwitterClientError) as exc_info:
            TwitterClient()

        assert "TWITTER_ACCESS_TOKEN" in str(exc_info.value)

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_missing_access_secret_raises_error(
        self, mock_settings: MagicMock
    ) -> None:
        """TwitterClient raises error when access secret missing."""
        mock_settings.TWITTER_API_KEY = "api_key"
        mock_settings.TWITTER_API_SECRET = "api_secret"
        mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
        mock_settings.TWITTER_ACCESS_SECRET = None

        with pytest.raises(TwitterClientError) as exc_info:
            TwitterClient()

        assert "TWITTER_ACCESS_SECRET" in str(exc_info.value)

    @patch("apps.event_processors.services.twitter_client.settings")
    def test_init_reports_all_missing_credentials(
        self, mock_settings: MagicMock
    ) -> None:
        """TwitterClient error lists all missing credentials."""
        mock_settings.TWITTER_API_KEY = None
        mock_settings.TWITTER_API_SECRET = None
        mock_settings.TWITTER_ACCESS_TOKEN = None
        mock_settings.TWITTER_ACCESS_SECRET = None

        with pytest.raises(TwitterClientError) as exc_info:
            TwitterClient()

        error_msg = str(exc_info.value)
        assert "TWITTER_API_KEY" in error_msg
        assert "TWITTER_API_SECRET" in error_msg
        assert "TWITTER_ACCESS_TOKEN" in error_msg
        assert "TWITTER_ACCESS_SECRET" in error_msg


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestTwitterClientCooldown:
    """Tests for cooldown enforcement."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_social_posts(self):
        """Clean up SocialPost records before each test."""
        await SocialPost.objects.filter(platform="twitter").adelete()
        yield
        await SocialPost.objects.filter(platform="twitter").adelete()

    def _create_mock_client(self) -> TwitterClient:
        """Create TwitterClient with mocked settings."""
        with patch(
            "apps.event_processors.services.twitter_client.settings"
        ) as mock_settings:
            mock_settings.TWITTER_API_KEY = "api_key"
            mock_settings.TWITTER_API_SECRET = "api_secret"
            mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
            mock_settings.TWITTER_ACCESS_SECRET = "access_secret"
            mock_settings.TWITTER_BEARER_TOKEN = None
            mock_settings.TWITTER_COOLDOWN_MINUTES = 30
            client = TwitterClient()
            return client

    @pytest_asyncio.fixture
    async def detected_event(self) -> DetectedEvent:
        """Create a DetectedEvent for testing."""
        return await DetectedEvent.objects.acreate(
            event_type="urination",
            channel_id="NODE3000004",
            detected_at=timezone.now(),
            confidence=Decimal("0.85"),
        )

    async def test_check_cooldown_no_posts_returns_true(self) -> None:
        """Cooldown check returns True when no posts exist."""
        mock_client = self._create_mock_client()
        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is True
        assert remaining is None

    async def test_check_cooldown_recent_post_blocks(
        self, detected_event: DetectedEvent
    ) -> None:
        """Cooldown check returns False when recent post exists."""
        mock_client = self._create_mock_client()
        await SocialPost.objects.acreate(
            event=detected_event,
            platform="twitter",
            external_id="12345",
            content="Recent post",
            posted_at=timezone.now() - timedelta(minutes=15),  # Within 30min
        )

        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is False
        assert remaining is not None
        assert remaining.total_seconds() > 0

    async def test_check_cooldown_old_post_allows(
        self, detected_event: DetectedEvent
    ) -> None:
        """Cooldown check returns True when only old posts exist."""
        mock_client = self._create_mock_client()
        await SocialPost.objects.acreate(
            event=detected_event,
            platform="twitter",
            external_id="12345",
            content="Old post",
            posted_at=timezone.now() - timedelta(minutes=45),  # Outside 30min
        )

        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is True
        assert remaining is None

    async def test_check_cooldown_only_checks_twitter_posts(
        self, detected_event: DetectedEvent
    ) -> None:
        """Cooldown check only considers twitter platform posts."""
        mock_client = self._create_mock_client()
        await SocialPost.objects.acreate(
            event=detected_event,
            platform="mastodon",  # Different platform
            external_id="12345",
            content="Mastodon post",
            posted_at=timezone.now() - timedelta(minutes=5),
        )

        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is True  # Should not block on mastodon posts


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestTwitterClientPost:
    """Tests for posting functionality."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_social_posts(self):
        """Clean up SocialPost records before each test."""
        await SocialPost.objects.filter(platform="twitter").adelete()
        yield
        await SocialPost.objects.filter(platform="twitter").adelete()

    def _create_mock_client(self) -> TwitterClient:
        """Create TwitterClient with mocked tweepy client."""
        with patch(
            "apps.event_processors.services.twitter_client.settings"
        ) as mock_settings:
            mock_settings.TWITTER_API_KEY = "api_key"
            mock_settings.TWITTER_API_SECRET = "api_secret"
            mock_settings.TWITTER_ACCESS_TOKEN = "access_token"
            mock_settings.TWITTER_ACCESS_SECRET = "access_secret"
            mock_settings.TWITTER_BEARER_TOKEN = None
            mock_settings.TWITTER_COOLDOWN_MINUTES = 30
            client = TwitterClient()
            client.client = MagicMock()
            return client

    @pytest_asyncio.fixture
    async def detected_event(self) -> DetectedEvent:
        """Create a DetectedEvent for testing."""
        return await DetectedEvent.objects.acreate(
            event_type="urination",
            channel_id="NODE3000004",
            detected_at=timezone.now(),
            confidence=Decimal("0.85"),
        )

    async def test_post_success_creates_social_post(
        self, detected_event: DetectedEvent
    ) -> None:
        """Successful post creates SocialPost record."""
        mock_client = self._create_mock_client()
        mock_response = MagicMock()
        mock_response.data = {"id": "1234567890"}
        mock_client.client.create_tweet.return_value = mock_response

        tweet_id = await mock_client.post("Test tweet content", detected_event)

        assert tweet_id == "1234567890"

        # Verify SocialPost was created
        social_post = await SocialPost.objects.filter(event=detected_event).afirst()
        assert social_post is not None
        assert social_post.platform == "twitter"
        assert social_post.external_id == "1234567890"
        assert social_post.content == "Test tweet content"

    async def test_post_during_cooldown_raises_error(
        self, detected_event: DetectedEvent
    ) -> None:
        """Posting during cooldown raises TwitterCooldownError."""
        mock_client = self._create_mock_client()
        # Create a recent post to trigger cooldown
        await SocialPost.objects.acreate(
            event=detected_event,
            platform="twitter",
            external_id="111",
            content="Previous post",
            posted_at=timezone.now() - timedelta(minutes=10),
        )

        with pytest.raises(TwitterCooldownError) as exc_info:
            await mock_client.post("Should not post", detected_event)

        assert "cooldown" in str(exc_info.value).lower()

    async def test_post_api_error_raises_client_error(
        self, detected_event: DetectedEvent
    ) -> None:
        """API error raises TwitterClientError."""
        mock_client = self._create_mock_client()
        from tweepy.errors import TweepyException

        mock_client.client.create_tweet.side_effect = TweepyException("API Error")

        with pytest.raises(TwitterClientError):
            await mock_client.post("Test content", detected_event)

    async def test_post_rate_limit_raises_specific_error(
        self, detected_event: DetectedEvent
    ) -> None:
        """Rate limit error raises TwitterRateLimitError."""
        mock_client = self._create_mock_client()
        from tweepy.errors import TweepyException

        # Create exception and set response attribute
        exc = TweepyException("Rate limit exceeded")
        mock_response = MagicMock()
        mock_response.status_code = 429
        exc.response = mock_response
        mock_client.client.create_tweet.side_effect = exc

        with pytest.raises(TwitterRateLimitError) as exc_info:
            await mock_client.post("Test content", detected_event)

        assert "rate limit" in str(exc_info.value).lower()

    async def test_post_empty_response_returns_none(
        self, detected_event: DetectedEvent
    ) -> None:
        """Empty API response returns None."""
        mock_client = self._create_mock_client()
        mock_response = MagicMock()
        mock_response.data = None
        mock_client.client.create_tweet.return_value = mock_response

        result = await mock_client.post("Test content", detected_event)

        assert result is None
