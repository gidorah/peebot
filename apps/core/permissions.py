from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsDebugMode(BasePermission):
    message = "Manual telemetry injection is disabled when DEBUG is False."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """
        Allow access only when the Django DEBUG setting is enabled.
        
        Parameters:
        	request (Request): The incoming HTTP request (not used by this permission).
        	view (APIView): The target view (not used by this permission).
        
        Returns:
        	bool: `True` if `settings.DEBUG` is True, `False` otherwise.
        """
        return settings.DEBUG
