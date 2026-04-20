"""Shared DRF serializer base classes.

Per FR-CORE-002 the ``core`` module hosts serializer primitives that are
reused across apps. Concrete telemetry serializers live in
``apps.telemetry_storage.serializers`` and
``apps.event_processors.serializers``.
"""

from rest_framework.serializers import ModelSerializer


class BaseTelemetrySerializer(ModelSerializer):
    """Project-wide base for telemetry-related DRF ``ModelSerializer`` s.

    Currently empty — acts as a single inheritance anchor so that
    cross-cutting serializer behavior (e.g. shared field renderers, camel-
    case conversion) can be introduced later in one place.
    """

    pass
