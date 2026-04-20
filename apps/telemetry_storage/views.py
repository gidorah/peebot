"""DRF viewsets exposing telemetry storage models over the public API."""

from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.telemetry_storage import repositories
from apps.telemetry_storage.serializers import TelemetryChannelSerializer


class TelemetryChannelViewSet(ReadOnlyModelViewSet):
    """Read-only viewset backing ``GET /api/v1/channels/``.

    Returns the currently active telemetry channels (soft-deleted channels
    are hidden via :class:`apps.core.models.ActiveModelManager`) sorted by
    ``public_pui`` for stable pagination.
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = TelemetryChannelSerializer

    def get_queryset(self):
        """Delegate to the repository so tests can substitute the data source."""
        return repositories.get_telemetry_channel_queryset()
