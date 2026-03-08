from apps.core.serializers import BaseTelemetrySerializer
from apps.event_processors.models import DetectedEvent


class DetectedEventSerializer(BaseTelemetrySerializer):
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
