"""DRF serializers exposing event-processor models over the public API.

Backs ``GET /api/v1/events/`` — a read-only listing of detected events
used by dashboards and external consumers. Social-post records are
deliberately not exposed via the public API today.
"""

from apps.core.serializers import BaseTelemetrySerializer
from apps.event_processors.models import DetectedEvent


class DetectedEventSerializer(BaseTelemetrySerializer):
    """Public representation of a :class:`DetectedEvent`.

    The ``metadata`` JSON field carries processor-specific detection
    details (trend points, confidence factors, etc.) and is passed
    through as-is.
    """

    class Meta:
        model = DetectedEvent
        fields = [
            "id",
            "event_type",
            "channel_id",
            "detected_at",
            "confidence",
            "metadata",
            "created_at",
        ]
