"""DRF views for the manual telemetry injection endpoint.

Backs ``POST /api/v1/telemetry/inject/`` (FR-ING-006) — a
development-only endpoint gated by
:class:`~apps.core.permissions.IsDebugMode` that lets contributors
inject synthetic readings against the same validation and persistence
path used by the live Lightstreamer pipeline.
"""

from __future__ import annotations

from django.db import IntegrityError
from pydantic import ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsDebugMode
from apps.telemetry_ingestion.services.injection import ManualInjectionPayload
from apps.telemetry_storage.repositories import DjangoTelemetryRepository
from apps.telemetry_storage.serializers import TelemetryReadingSerializer


def _is_duplicate_reading_error(error: IntegrityError) -> bool:
    """Return ``True`` when ``error`` is the ``(channel, timestamp)`` uniqueness violation.

    The constraint is introduced by ADR-011 to deduplicate Lightstreamer
    snapshot re-broadcasts. Manual injection should translate it into an
    HTTP 409 rather than a 500.

    Args:
        error: The :class:`IntegrityError` raised by the ORM.

    Returns:
        ``True`` when the error's underlying psycopg diagnostic, or its
        stringified form, names the ``unique_channel_timestamp`` constraint.
    """
    cause = error.__cause__
    if cause is not None:
        diag = getattr(cause, "diag", None)
        if getattr(diag, "constraint_name", None) == "unique_channel_timestamp":
            return True

    return "unique_channel_timestamp" in str(error)


class InjectTelemetryView(APIView):
    """Debug-only endpoint that inserts a single hand-crafted telemetry reading.

    Permits only when ``settings.DEBUG`` is ``True`` so the route is
    implicitly disabled in production deployments regardless of URL
    configuration.
    """

    permission_classes = [IsDebugMode]

    def post(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Validate the payload, resolve the channel, and persist the reading.

        Returns 201 on success with the serialized reading; 400 on schema
        validation failure; 404 when the PUI does not resolve to a
        known channel; 409 when a reading with the same
        ``(channel, timestamp)`` already exists.
        """
        try:
            payload = ManualInjectionPayload.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"errors": exc.errors(include_url=False)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        repository = DjangoTelemetryRepository()
        channel = repository.get_channel_by_public_pui(payload.pui)

        if channel is None:
            return Response(
                {"detail": "Telemetry channel not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            reading = repository.create_reading(payload.to_reading_data(channel))
        except IntegrityError as exc:
            if _is_duplicate_reading_error(exc):
                return Response(
                    {
                        "detail": "Telemetry reading already exists for this channel and timestamp."
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            raise

        serializer = TelemetryReadingSerializer(reading)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
