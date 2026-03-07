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
