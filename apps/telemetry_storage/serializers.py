"""DRF serializers exposing telemetry storage models over the public API.

These serializers power the read-only ``/api/v1/channels/`` endpoint and
are also used to shape dashboard responses. They deliberately omit
soft-delete and system-maintenance fields that are not useful to external
consumers.
"""

from apps.core.serializers import BaseTelemetrySerializer
from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


class TelemetryChannelSerializer(BaseTelemetrySerializer):
    """Public representation of a :class:`TelemetryChannel`."""

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
    """Public representation of a :class:`TelemetryReading`.

    Includes ingestion-timestamp (``created_at``) so dashboard clients can
    distinguish "time of measurement" (``timestamp``) from "time of
    persistence" (``created_at``) — useful when evaluating ingestion
    latency per NFR-PERF-002.
    """

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
