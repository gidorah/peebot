"""Tests for the BlueskyClient service.

Verifies cooldown enforcement, posting functionality, error handling,
and SocialPost record creation.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from django.utils import timezone

from apps.event_processors.models import DetectedEvent, SocialPost
from apps.event_processors.services.bluesky_client import (
    BlueskyClient,
    BlueskyClientError,
    BlueskyCooldownError,
)


@pytest_asyncio.fixture
async def detected_event() -> DetectedEvent:
    """Create a DetectedEvent for testing."""
    return await DetectedEvent.objects.acreate(
        event_type="urination",
        channel_id="NODE3000005",
        detected_at=timezone.now(),
        confidence=Decimal("0.85"),
    )


def _create_mock_client() -> BlueskyClient:
    """Create BlueskyClient with mocked atproto client."""
    with (
        patch(
            "apps.event_processors.services.bluesky_client.settings"
        ) as mock_settings,
        patch("apps.event_processors.services.bluesky_client.Client") as mock_client,
    ):
        mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
        mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"
        mock_settings.BLUESKY_COOLDOWN_MINUTES = 30
        mock_atproto = MagicMock()
        mock_client.return_value = mock_atproto
        client = BlueskyClient()
        client._authenticated = True
        return client


def _get_send_post_mock(client: BlueskyClient) -> MagicMock:
    """Return the mocked send_post method for assertions and stubbing."""
    return cast(MagicMock, client.client.send_post)


class TestBlueskyClientTruncation:
    """Tests for the _truncate_to_grapheme_limit static method."""

    def test_short_text_unchanged(self) -> None:
        """Text within the limit is returned unchanged."""
        text = "Hello, ISS!"
        assert BlueskyClient._truncate_to_grapheme_limit(text) == text

    def test_exactly_300_chars_unchanged(self) -> None:
        """Text of exactly 300 characters is returned unchanged."""
        text = "x" * 300
        assert BlueskyClient._truncate_to_grapheme_limit(text) == text

    def test_301_chars_truncated_with_ellipsis(self) -> None:
        """Text of 301 characters is truncated to 299 chars + ellipsis."""
        text = "x" * 301
        result = BlueskyClient._truncate_to_grapheme_limit(text)
        assert len(result) == 300
        assert result.endswith("\u2026")
        assert result == "x" * 299 + "\u2026"

    def test_long_text_truncated_to_300(self) -> None:
        """Long text is truncated so result has exactly 300 code points."""
        text = "a" * 500
        result = BlueskyClient._truncate_to_grapheme_limit(text)
        assert len(result) == 300
        assert result.endswith("\u2026")

    def test_empty_string_unchanged(self) -> None:
        """Empty string is returned unchanged."""
        assert BlueskyClient._truncate_to_grapheme_limit("") == ""

    def test_truncation_with_unicode_emoji(self) -> None:
        """Text with simple emoji (single code points) is truncated correctly."""
        # 😂 is a single code point, so len("😂") == 1
        text = "😂" * 301
        result = BlueskyClient._truncate_to_grapheme_limit(text)
        assert len(result) == 300
        assert result.endswith("\u2026")


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestBlueskyClientPostTruncation:
    """Tests that post() truncates long text before posting."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_social_posts(self):
        """Clean up SocialPost records before and after each test."""
        await SocialPost.objects.filter(platform="bluesky").adelete()
        yield
        await SocialPost.objects.filter(platform="bluesky").adelete()

    async def test_post_long_text_sends_truncated_text(
        self, detected_event: DetectedEvent
    ) -> None:
        """post() sends truncated text to Bluesky when text exceeds 300 graphemes."""
        mock_client = _create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:xxx/app.bsky.feed.post/yyy"
        send_post.return_value = mock_response

        long_text = "a" * 350

        await mock_client.post(long_text, detected_event)

        call_args = send_post.call_args
        actual_text = call_args.kwargs["text"]
        assert len(actual_text) == 300
        assert actual_text.endswith("\u2026")

    async def test_post_long_text_stores_truncated_content(
        self, detected_event: DetectedEvent
    ) -> None:
        """post() stores the truncated text in SocialPost.content."""
        mock_client = _create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:xxx/app.bsky.feed.post/yyy"
        send_post.return_value = mock_response

        long_text = "b" * 350

        await mock_client.post(long_text, detected_event)

        social_post = await SocialPost.objects.filter(event=detected_event).afirst()
        assert social_post is not None
        assert len(social_post.content) == 300
        assert social_post.content.endswith("\u2026")

    async def test_post_within_limit_sends_unchanged_text(
        self, detected_event: DetectedEvent
    ) -> None:
        """post() sends text unchanged when it is within the 300-grapheme limit."""
        mock_client = _create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:xxx/app.bsky.feed.post/yyy"
        send_post.return_value = mock_response

        short_text = "Hello, this is a short post!"

        await mock_client.post(short_text, detected_event)

        call_args = send_post.call_args
        assert call_args.kwargs["text"] == short_text


class TestBlueskyClientInitialization:
    """Tests for BlueskyClient initialization."""

    @patch("apps.event_processors.services.bluesky_client.Client")
    @patch("apps.event_processors.services.bluesky_client.settings")
    def test_init_with_all_credentials(
        self, mock_settings: MagicMock, mock_client_class: MagicMock
    ) -> None:
        """BlueskyClient initializes with all required credentials."""
        mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
        mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"
        mock_settings.BLUESKY_COOLDOWN_MINUTES = None

        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        client = BlueskyClient()

        assert client.client is not None
        assert client.cooldown_minutes == 30  # Default
        assert client._authenticated is False
        assert client._handle == "peebot.bsky.social"
        mock_client.login.assert_not_called()

    @patch("apps.event_processors.services.bluesky_client.Client")
    @patch("apps.event_processors.services.bluesky_client.settings")
    def test_init_with_custom_cooldown(
        self, mock_settings: MagicMock, mock_client_class: MagicMock
    ) -> None:
        """BlueskyClient uses custom cooldown when provided."""
        mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
        mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"
        mock_settings.BLUESKY_COOLDOWN_MINUTES = 60

        mock_client_class.return_value = MagicMock()

        client = BlueskyClient()

        assert client.cooldown_minutes == 60

    @patch("apps.event_processors.services.bluesky_client.settings")
    def test_init_missing_handle_raises_error(self, mock_settings: MagicMock) -> None:
        """BlueskyClient raises error when handle missing."""
        mock_settings.BLUESKY_HANDLE = None
        mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"

        with pytest.raises(BlueskyClientError) as exc_info:
            BlueskyClient()

        assert "BLUESKY_HANDLE" in str(exc_info.value)

    @patch("apps.event_processors.services.bluesky_client.settings")
    def test_init_missing_app_password_raises_error(
        self, mock_settings: MagicMock
    ) -> None:
        """BlueskyClient raises error when app password missing."""
        mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
        mock_settings.BLUESKY_APP_PASSWORD = None

        with pytest.raises(BlueskyClientError) as exc_info:
            BlueskyClient()

        assert "BLUESKY_APP_PASSWORD" in str(exc_info.value)

    @patch("apps.event_processors.services.bluesky_client.settings")
    def test_init_reports_all_missing_credentials(
        self, mock_settings: MagicMock
    ) -> None:
        """BlueskyClient error lists all missing credentials."""
        mock_settings.BLUESKY_HANDLE = None
        mock_settings.BLUESKY_APP_PASSWORD = None

        with pytest.raises(BlueskyClientError) as exc_info:
            BlueskyClient()

        error_msg = str(exc_info.value)
        assert "BLUESKY_HANDLE" in error_msg
        assert "BLUESKY_APP_PASSWORD" in error_msg

    @pytest.mark.asyncio
    @patch("apps.event_processors.services.bluesky_client.Client")
    @patch("apps.event_processors.services.bluesky_client.settings")
    async def test_ensure_authenticated_login_failure_raises_error(
        self, mock_settings: MagicMock, mock_client_class: MagicMock
    ) -> None:
        """_ensure_authenticated raises error when login fails."""
        from atproto.exceptions import AtProtocolError

        mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
        mock_settings.BLUESKY_APP_PASSWORD = "wrong-password"
        mock_settings.BLUESKY_COOLDOWN_MINUTES = None

        mock_client = MagicMock()
        mock_client.login.side_effect = AtProtocolError("Invalid credentials")
        mock_client_class.return_value = mock_client

        client = BlueskyClient()

        with pytest.raises(BlueskyClientError) as exc_info:
            await client._ensure_authenticated()

        assert "authenticate" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("apps.event_processors.services.bluesky_client.Client")
    @patch("apps.event_processors.services.bluesky_client.settings")
    async def test_ensure_authenticated_network_error_raises_client_error(
        self, mock_settings: MagicMock, mock_client_class: MagicMock
    ) -> None:
        """_ensure_authenticated wraps network errors (e.g. DNS failure) as BlueskyClientError.

        Previously, non-AtProtocolError exceptions (such as OSError from a temporary
        DNS resolution failure) would propagate unhandled and be logged at ERROR level,
        creating Sentry noise. They must now be wrapped as BlueskyClientError so callers
        can treat them as ordinary (WARNING-level) service failures.
        """
        mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
        mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"
        mock_settings.BLUESKY_COOLDOWN_MINUTES = None

        mock_client = MagicMock()
        mock_client.login.side_effect = OSError(
            "[Errno -3] Temporary failure in name resolution"
        )
        mock_client_class.return_value = mock_client

        client = BlueskyClient()

        with pytest.raises(BlueskyClientError) as exc_info:
            await client._ensure_authenticated()

        assert "authenticate" in str(exc_info.value).lower()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestBlueskyClientCooldown:
    """Tests for cooldown enforcement."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_social_posts(self):
        """Clean up SocialPost records before each test."""
        await SocialPost.objects.filter(platform="bluesky").adelete()
        yield
        await SocialPost.objects.filter(platform="bluesky").adelete()

    def _create_mock_client(self) -> BlueskyClient:
        """Create BlueskyClient with mocked settings."""
        with (
            patch(
                "apps.event_processors.services.bluesky_client.settings"
            ) as mock_settings,
            patch(
                "apps.event_processors.services.bluesky_client.Client"
            ) as mock_client,
        ):
            mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
            mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"
            mock_settings.BLUESKY_COOLDOWN_MINUTES = 30
            mock_client.return_value = MagicMock()
            client = BlueskyClient()
            client._authenticated = True
            return client

    @pytest_asyncio.fixture
    async def detected_event(self) -> DetectedEvent:
        """Create a DetectedEvent for testing."""
        return await DetectedEvent.objects.acreate(
            event_type="urination",
            channel_id="NODE3000005",
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
            platform="bluesky",
            external_id="at://did:plc:xxx/app.bsky.feed.post/yyy",
            content="Recent post",
            posted_at=timezone.now() - timedelta(minutes=15),  # Within 30min
            status=SocialPost.Status.SUCCESS,
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
            platform="bluesky",
            external_id="at://did:plc:xxx/app.bsky.feed.post/yyy",
            content="Old post",
            posted_at=timezone.now() - timedelta(minutes=45),  # Outside 30min
            status=SocialPost.Status.SUCCESS,
        )

        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is True
        assert remaining is None

    async def test_check_cooldown_only_checks_bluesky_posts(
        self, detected_event: DetectedEvent
    ) -> None:
        """Cooldown check only considers bluesky platform posts."""
        mock_client = self._create_mock_client()
        await SocialPost.objects.acreate(
            event=detected_event,
            platform="twitter",  # Different platform
            external_id="12345",
            content="Twitter post",
            posted_at=timezone.now() - timedelta(minutes=5),
            status=SocialPost.Status.SUCCESS,
        )

        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is True  # Should not block on twitter posts

    async def test_failed_post_does_not_trigger_cooldown(
        self, detected_event: DetectedEvent
    ) -> None:
        """Failed posts do not count toward cooldown."""
        mock_client = self._create_mock_client()

        await SocialPost.objects.acreate(
            event=detected_event,
            platform="bluesky",
            external_id="",
            content="Failed post",
            posted_at=None,
            status=SocialPost.Status.FAILED,
            error_message="Some error",
        )

        can_post, remaining = await mock_client.check_cooldown()

        assert can_post is True
        assert remaining is None

    async def test_check_cooldown_db_error_is_non_fatal_and_blocks_post(self) -> None:
        """A transient DB error in check_cooldown blocks posting but does NOT log at ERROR.

        Logging at ERROR would create a Sentry event via LoggingIntegration(event_level=ERROR)
        for every DNS hiccup. The method must log at WARNING and return a conservative
        (block-posting) result so the task can continue safely.
        """
        from unittest.mock import patch as mock_patch

        import structlog.testing

        mock_client = self._create_mock_client()

        with (
            mock_patch(
                "apps.event_processors.services.bluesky_client.SocialPost.objects.filter",
                side_effect=Exception("[Errno -3] Temporary failure in name resolution"),
            ),
            structlog.testing.capture_logs() as captured,
        ):
            can_post, remaining = await mock_client.check_cooldown()

        assert can_post is False
        assert remaining is not None

        # Must be logged at WARNING, not ERROR, to avoid generating a Sentry event.
        warning_logs = [e for e in captured if e.get("log_level") == "warning"]
        assert any(
            "bluesky_cooldown_check_failed" in e.get("event", "") for e in warning_logs
        ), "Expected a warning-level log for cooldown check failure"

        error_logs = [e for e in captured if e.get("log_level") == "error"]
        assert not any(
            "bluesky_cooldown_check_failed" in e.get("event", "") for e in error_logs
        ), "cooldown check failure must NOT be logged at error level"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestBlueskyClientPost:
    """Tests for posting functionality."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_social_posts(self):
        """Clean up SocialPost records before each test."""
        await SocialPost.objects.filter(platform="bluesky").adelete()
        yield
        await SocialPost.objects.filter(platform="bluesky").adelete()

    def _create_mock_client(self) -> BlueskyClient:
        """Create BlueskyClient with mocked atproto client."""
        with (
            patch(
                "apps.event_processors.services.bluesky_client.settings"
            ) as mock_settings,
            patch(
                "apps.event_processors.services.bluesky_client.Client"
            ) as mock_client,
        ):
            mock_settings.BLUESKY_HANDLE = "peebot.bsky.social"
            mock_settings.BLUESKY_APP_PASSWORD = "app-password-123"
            mock_settings.BLUESKY_COOLDOWN_MINUTES = 30
            mock_atproto = MagicMock()
            mock_client.return_value = mock_atproto
            client = BlueskyClient()
            client._authenticated = True
            return client

    @pytest_asyncio.fixture
    async def detected_event(self) -> DetectedEvent:
        """Create a DetectedEvent for testing."""
        return await DetectedEvent.objects.acreate(
            event_type="urination",
            channel_id="NODE3000005",
            detected_at=timezone.now(),
            confidence=Decimal("0.85"),
        )

    async def test_post_success_creates_social_post(
        self, detected_event: DetectedEvent
    ) -> None:
        """Successful post creates SocialPost record."""
        mock_client = self._create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:xxx/app.bsky.feed.post/yyy"
        mock_response.cid = "bafyreiabc123"
        send_post.return_value = mock_response

        post_uri = await mock_client.post("Test post content", detected_event)

        assert post_uri == "at://did:plc:xxx/app.bsky.feed.post/yyy"

        social_post = await SocialPost.objects.filter(event=detected_event).afirst()
        assert social_post is not None
        assert social_post.platform == "bluesky"
        assert social_post.external_id == "at://did:plc:xxx/app.bsky.feed.post/yyy"
        assert social_post.content == "Test post content"
        assert social_post.status == SocialPost.Status.SUCCESS

    async def test_post_during_cooldown_raises_error(
        self, detected_event: DetectedEvent
    ) -> None:
        """Posting during cooldown raises BlueskyCooldownError."""
        mock_client = self._create_mock_client()
        await SocialPost.objects.acreate(
            event=detected_event,
            platform="bluesky",
            external_id="at://did:plc:xxx/app.bsky.feed.post/previous",
            content="Previous post",
            posted_at=timezone.now() - timedelta(minutes=10),
            status=SocialPost.Status.SUCCESS,
        )

        with pytest.raises(BlueskyCooldownError) as exc_info:
            await mock_client.post("Should not post", detected_event)

        assert "cooldown" in str(exc_info.value).lower()

    async def test_post_api_error_raises_client_error(
        self, detected_event: DetectedEvent
    ) -> None:
        """API error raises BlueskyClientError."""
        from atproto.exceptions import AtProtocolError

        mock_client = self._create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        send_post.side_effect = AtProtocolError("API Error")

        with pytest.raises(BlueskyClientError):
            await mock_client.post("Test content", detected_event)

    async def test_post_empty_response_returns_none(
        self, detected_event: DetectedEvent
    ) -> None:
        """Empty API response returns None and creates failed SocialPost."""
        mock_client = self._create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        mock_response = MagicMock()
        mock_response.uri = None
        send_post.return_value = mock_response

        result = await mock_client.post("Test content", detected_event)

        assert result is None

        social_post = await SocialPost.objects.filter(event=detected_event).afirst()
        assert social_post is not None
        assert social_post.status == SocialPost.Status.FAILED
        assert social_post.external_id == ""
        assert "No response" in social_post.error_message

    async def test_post_api_error_creates_failed_social_post(
        self, detected_event: DetectedEvent
    ) -> None:
        """API error creates SocialPost with failed status."""
        from atproto.exceptions import AtProtocolError

        mock_client = self._create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        send_post.side_effect = AtProtocolError("API Error")

        with pytest.raises(BlueskyClientError):
            await mock_client.post("Test content", detected_event)

        social_post = await SocialPost.objects.filter(event=detected_event).afirst()
        assert social_post is not None
        assert social_post.status == SocialPost.Status.FAILED
        assert social_post.content == "Test content"
        assert "API error" in social_post.error_message

    async def test_successful_post_has_success_status(
        self, detected_event: DetectedEvent
    ) -> None:
        """Successful post creates SocialPost with success status."""
        mock_client = self._create_mock_client()
        send_post = _get_send_post_mock(mock_client)
        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:xxx/app.bsky.feed.post/zzz"
        send_post.return_value = mock_response

        await mock_client.post("Test post", detected_event)

        social_post = await SocialPost.objects.filter(event=detected_event).afirst()
        assert social_post is not None
        assert social_post.status == SocialPost.Status.SUCCESS
        assert social_post.external_id == "at://did:plc:xxx/app.bsky.feed.post/zzz"
        assert social_post.error_message == ""
