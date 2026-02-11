"""Event Processors Data Models.

This module defines the persistence layer for the analytics framework:
- DetectedEvent: Stores detected ISS operational events
- ProcessorState: Maintains processor state for resumption/replay
- SocialPost: Tracks social media posts linked to events
"""

from django.db import models

from apps.core.models import TimeStampedModel, UUID7Model


class DetectedEvent(UUID7Model, TimeStampedModel):
    """Stores analytics results from event processors.

    Generic model supporting all processor types (urination, temp spikes, etc.).
    The metadata field stores processor-specific detection details.
    """

    event_type = models.CharField(
        max_length=50,
        help_text="Event category (e.g., 'urination', 'temp_spike')",
    )
    channel_id = models.CharField(
        max_length=50,
        help_text="PUI of source channel (e.g., 'NODE3000004')",
    )
    detected_at = models.DateTimeField(
        help_text="Logical timestamp of event occurrence",
    )
    confidence = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Detection confidence (0.00-1.00)",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Processor-specific detection details (trend data, thresholds, etc.)",
    )

    class Meta:
        indexes = [
            models.Index(fields=["event_type", "-detected_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.detected_at} ({self.confidence})"


class ProcessorState(UUID7Model, TimeStampedModel):
    """Maintains processor state for resumption and historical replay.

    Each processor has a single row identified by processor_name.
    The last_processed_timestamp cursor enables resumption after restarts.
    """

    processor_name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique processor identifier",
    )
    last_processed_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successfully analyzed data timestamp",
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last execution start time",
    )
    state_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Processor-specific state data",
    )

    def __str__(self) -> str:
        return f"{self.processor_name} (last run: {self.last_run_at})"


class SocialPost(UUID7Model, TimeStampedModel):
    """Tracks social media posts linked to detected events.

    Supports multiple platforms and enables cooldown enforcement
    by querying recent posts per platform.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    event = models.ForeignKey(
        DetectedEvent,
        on_delete=models.CASCADE,
        related_name="social_posts",
        help_text="Reference to the triggering DetectedEvent",
    )
    platform = models.CharField(
        max_length=50,
        help_text="Social platform (e.g., 'bluesky')",
    )
    external_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Platform-specific post ID (e.g., Bluesky post URI). Empty if failed.",  # noqa: E501
    )
    content = models.TextField(
        help_text="The posted text content",
    )
    posted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the post was published. Null if failed.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Post status: pending, success, or failed",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error message if post failed",
    )

    class Meta:
        indexes = [
            models.Index(fields=["platform", "-posted_at"]),
            models.Index(fields=["platform", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.platform}: {self.external_id or 'N/A'} "
            f"({self.status}) @ {self.posted_at}"
        )
