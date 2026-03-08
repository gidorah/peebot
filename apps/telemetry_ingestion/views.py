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
    cause = error.__cause__
    if cause is not None:
        diag = getattr(cause, "diag", None)
        if getattr(diag, "constraint_name", None) == "unique_channel_timestamp":
            return True

    return "unique_channel_timestamp" in str(error)


class InjectTelemetryView(APIView):
    permission_classes = [IsDebugMode]

    def post(self, request: Request, *args: object, **kwargs: object) -> Response:
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
