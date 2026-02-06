"""Tests for event_processors models.

Verifies CRUD operations, constraints, and index existence for:
- ProcessorState
- DetectedEvent
- SocialPost
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection
from django.utils import timezone

from apps.event_processors.models import DetectedEvent, ProcessorState, SocialPost


@pytest.mark.django_db
class TestProcessorState:
    """Tests for the ProcessorState model."""

    def test_create_processor_state(self) -> None:
        """ProcessorState can be created with required fields."""
        state = ProcessorState.objects.create(
            processor_name="test_processor",
            last_processed_at=timezone.now(),
            last_run_at=timezone.now(),
        )
        assert state.id is not None
        assert state.processor_name == "test_processor"
        assert state.created_at is not None
        assert state.updated_at is not None

    def test_unique_processor_name_constraint(self) -> None:
        """processor_name must be unique."""
        ProcessorState.objects.create(processor_name="unique_processor")
        with pytest.raises(IntegrityError):
            ProcessorState.objects.create(processor_name="unique_processor")

    def test_state_persistence(self) -> None:
        """State can be updated and persisted."""
        state = ProcessorState.objects.create(
            processor_name="persist_test",
            state_data={"cursor": 0},
        )
        state.state_data = {"cursor": 100}
        state.save()

        reloaded = ProcessorState.objects.get(processor_name="persist_test")
        assert reloaded.state_data == {"cursor": 100}

    def test_nullable_fields(self) -> None:
        """Optional fields can be null."""
        state = ProcessorState.objects.create(processor_name="minimal_processor")
        assert state.last_processed_at is None
        assert state.last_run_at is None
        assert state.state_data is None


@pytest.mark.django_db
class TestDetectedEvent:
    """Tests for the DetectedEvent model."""

    def test_create_detected_event(self) -> None:
        """DetectedEvent can be created with all required fields."""
        event = DetectedEvent.objects.create(
            event_type="urination",
            channel_id="NODE3000004",
            detected_at=timezone.now(),
            confidence=Decimal("0.85"),
            metadata={"burst_duration_seconds": 45},
        )
        assert event.id is not None
        assert event.event_type == "urination"
        assert event.confidence == Decimal("0.85")

    def test_metadata_default(self) -> None:
        """metadata defaults to empty dict."""
        event = DetectedEvent.objects.create(
            event_type="test_event",
            channel_id="TEST001",
            detected_at=timezone.now(),
            confidence=Decimal("0.50"),
        )
        assert event.metadata == {}

    def test_event_type_detected_at_index_exists(self) -> None:
        """Index on (event_type, -detected_at) should exist."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'event_processors_detectedevent'
                AND indexdef LIKE '%event_type%'
                AND indexdef LIKE '%detected_at%'
            """)
            result = cursor.fetchall()
        assert len(result) >= 1, "Index on (event_type, -detected_at) not found"


@pytest.mark.django_db
class TestSocialPost:
    """Tests for the SocialPost model."""

    @pytest.fixture
    def detected_event(self) -> DetectedEvent:
        """Create a DetectedEvent for FK relationship tests."""
        return DetectedEvent.objects.create(
            event_type="urination",
            channel_id="NODE3000004",
            detected_at=timezone.now(),
            confidence=Decimal("0.90"),
        )

    def test_create_social_post(self, detected_event: DetectedEvent) -> None:
        """SocialPost can be created with FK to DetectedEvent."""
        post = SocialPost.objects.create(
            event=detected_event,
            platform="bluesky",
            external_id="1234567890",
            content="ISS crew member just used the facilities!",
            posted_at=timezone.now(),
        )
        assert post.id is not None
        assert post.event == detected_event
        assert post.platform == "bluesky"

    def test_fk_relationship(self, detected_event: DetectedEvent) -> None:
        """DetectedEvent can access related social posts."""
        SocialPost.objects.create(
            event=detected_event,
            platform="bluesky",
            external_id="111",
            content="Post 1",
            posted_at=timezone.now(),
        )
        SocialPost.objects.create(
            event=detected_event,
            platform="mastodon",
            external_id="222",
            content="Toot 1",
            posted_at=timezone.now(),
        )
        assert detected_event.social_posts.count() == 2

    def test_cooldown_query(self, detected_event: DetectedEvent) -> None:
        """Posts within last 30 minutes can be queried for cooldown logic."""
        now = timezone.now()
        old_post = SocialPost.objects.create(
            event=detected_event,
            platform="bluesky",
            external_id="old",
            content="Old post",
            posted_at=now - timedelta(minutes=45),
        )
        recent_post = SocialPost.objects.create(
            event=detected_event,
            platform="bluesky",
            external_id="recent",
            content="Recent post",
            posted_at=now - timedelta(minutes=15),
        )

        cooldown_threshold = now - timedelta(minutes=30)
        recent_bluesky_posts = SocialPost.objects.filter(
            platform="bluesky",
            posted_at__gte=cooldown_threshold,
        )

        assert recent_post in recent_bluesky_posts
        assert old_post not in recent_bluesky_posts

    def test_platform_posted_at_index_exists(self) -> None:
        """Index on (platform, -posted_at) should exist."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'event_processors_socialpost'
                AND indexdef LIKE '%platform%'
                AND indexdef LIKE '%posted_at%'
            """)
            result = cursor.fetchall()
        assert len(result) >= 1, "Index on (platform, -posted_at) not found"

    def test_cascade_delete(self, detected_event: DetectedEvent) -> None:
        """SocialPosts are deleted when parent DetectedEvent is deleted."""
        SocialPost.objects.create(
            event=detected_event,
            platform="bluesky",
            external_id="cascade_test",
            content="Will be deleted",
            posted_at=timezone.now(),
        )
        event_id = detected_event.id
        detected_event.delete()

        assert not SocialPost.objects.filter(event_id=event_id).exists()
