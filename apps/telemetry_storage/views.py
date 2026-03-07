from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.telemetry_storage.models import TelemetryChannel
from apps.telemetry_storage.serializers import TelemetryChannelSerializer


class TelemetryChannelViewSet(ReadOnlyModelViewSet):
    queryset = TelemetryChannel.objects.order_by("public_pui")
    serializer_class = TelemetryChannelSerializer
