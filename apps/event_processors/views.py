"""Views for the event_processors module."""

from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.event_processors.models import DetectedEvent
from apps.event_processors.serializers import DetectedEventSerializer


class DetectedEventViewSet(ReadOnlyModelViewSet):
    """Read-only viewset backing ``GET /api/v1/events/``.

    Lists detected events (most recent first). Each entry corresponds to
    one successful processor run that identified an event — e.g. a UPA
    tank-fill pattern (FR-PROC-003). Social-post records associated with
    events are not exposed here.
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    queryset = DetectedEvent.objects.order_by("-detected_at")
    serializer_class = DetectedEventSerializer
