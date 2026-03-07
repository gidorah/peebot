from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.telemetry_storage import repositories
from apps.telemetry_storage.serializers import TelemetryChannelSerializer


class TelemetryChannelViewSet(ReadOnlyModelViewSet):
    serializer_class = TelemetryChannelSerializer

    def get_queryset(self):
        return repositories.get_telemetry_channel_queryset()
