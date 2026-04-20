"""DRF permission classes shared across PeeBot's REST endpoints."""

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsDebugMode(BasePermission):
    """Allow access only when ``settings.DEBUG`` is ``True``.

    Used to gate development-only endpoints such as the manual telemetry
    injection view (``POST /api/v1/telemetry/inject/``) per FR-ING-006, so
    the endpoint is automatically disabled in production regardless of
    URL routing.
    """

    message = "Manual telemetry injection is disabled when DEBUG is False."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return ``True`` when Django is running with ``DEBUG=True``."""
        return settings.DEBUG
