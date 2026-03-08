from apps.core.serializers import BaseTelemetrySerializer
from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


class TelemetryChannelSerializer(BaseTelemetrySerializer):
    class Meta:
        model = TelemetryChannel
        fields = [
            "id",
            "public_pui",
            "description",
            "ops_nom",
            "eng_nom",
            "unit",
        ]


class TelemetryReadingSerializer(BaseTelemetrySerializer):
    class Meta:
        model = TelemetryReading
        fields = [
            "id",
            "channel",
            "timestamp",
            "value",
            "calibrated_data",
            "status_class",
            "status_indicator",
            "status_color",
            "created_at",
        ]
