from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsDebugMode(BasePermission):
    message = "Manual telemetry injection is disabled when DEBUG is False."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return settings.DEBUG
