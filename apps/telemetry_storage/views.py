from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.telemetry_storage.models import TelemetryChannel
from apps.telemetry_storage.serializers import TelemetryChannelSerializer


class TelemetryChannelViewSet(ReadOnlyModelViewSet):
    queryset = TelemetryChannel.objects.all()
    serializer_class = TelemetryChannelSerializer
