from __future__ import annotations

from pydantic import ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsDebugMode
from apps.telemetry_ingestion.services.injection import ManualInjectionPayload
from apps.telemetry_storage.models import TelemetryChannel
from apps.telemetry_storage.repositories import DjangoTelemetryRepository
from apps.telemetry_storage.serializers import TelemetryReadingSerializer


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

        try:
            channel = TelemetryChannel.objects.get(public_pui=payload.pui)
        except TelemetryChannel.DoesNotExist:
            return Response(
                {"detail": "Telemetry channel not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        reading = DjangoTelemetryRepository().create_reading(
            payload.to_reading_data(channel)
        )
        serializer = TelemetryReadingSerializer(reading)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
