"""URL conf for PeeBot's versioned public REST API (``/api/v1/``).

Registered routes:

* ``GET /channels/`` — paginated telemetry channel listing (read-only).
* ``GET /events/`` — paginated detected events listing (read-only).
* ``POST /telemetry/inject/`` — manual telemetry injection, gated by
  ``DEBUG=True`` (FR-ING-006).

The OpenAPI schema and Swagger UI are mounted by the project-level
``config/urls.py`` at ``/api/schema/`` and ``/api/docs/``.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.event_processors.views import DetectedEventViewSet
from apps.telemetry_ingestion.views import InjectTelemetryView
from apps.telemetry_storage.views import TelemetryChannelViewSet

router = DefaultRouter()
router.register("channels", TelemetryChannelViewSet, basename="channel")
router.register("events", DetectedEventViewSet, basename="event")

urlpatterns = [
    *router.urls,
    path("telemetry/inject/", InjectTelemetryView.as_view(), name="telemetry-inject"),
]
