"""Views for the event_processors module."""

from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.event_processors.models import DetectedEvent
from apps.event_processors.serializers import DetectedEventSerializer


class DetectedEventViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    queryset = DetectedEvent.objects.order_by("-detected_at")
    serializer_class = DetectedEventSerializer
