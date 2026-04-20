"""Tests for the ``ManualInjectionPayload`` Pydantic schema and injection endpoint."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading
from apps.telemetry_storage.repositories import DjangoTelemetryRepository


def _payload() -> dict[str, str]:
    return {
        "pui": "NODE3000005",
        "timestamp": timezone.now().isoformat(),
        "value": "42.5",
        "status_class": "normal",
        "status_indicator": "steady",
        "status_color": "green",
    }


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_inject_success_201() -> None:
    channel = baker.make(TelemetryChannel, public_pui="NODE3000005")
    client = APIClient()

    response = client.post("/api/v1/telemetry/inject/", _payload(), format="json")

    assert response.status_code == 201
    reading = TelemetryReading.objects.get(channel=channel)
    assert reading.value == Decimal("42.5")
    assert response.json()["id"] == str(reading.id)


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_inject_duplicate_reading_409() -> None:
    baker.make(TelemetryChannel, public_pui="NODE3000005")
    client = APIClient()
    payload = _payload()

    first_response = client.post("/api/v1/telemetry/inject/", payload, format="json")
    second_response = client.post("/api/v1/telemetry/inject/", payload, format="json")

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Telemetry reading already exists for this channel and timestamp."
    }


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_inject_uses_repository_lookup() -> None:
    channel = baker.make(TelemetryChannel, public_pui="NODE3000005")
    client = APIClient()

    with patch.object(
        DjangoTelemetryRepository,
        "get_channel_by_public_pui",
        autospec=True,
        return_value=channel,
    ) as mock_get_channel:
        response = client.post("/api/v1/telemetry/inject/", _payload(), format="json")

    assert response.status_code == 201
    mock_get_channel.assert_called_once()
    assert mock_get_channel.call_args.args[1] == "NODE3000005"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_inject_unknown_pui_404() -> None:
    client = APIClient()

    response = client.post("/api/v1/telemetry/inject/", _payload(), format="json")

    assert response.status_code == 404
    assert response.json() == {"detail": "Telemetry channel not found."}


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_inject_missing_field_400() -> None:
    baker.make(TelemetryChannel, public_pui="NODE3000005")
    client = APIClient()
    payload = _payload()
    payload.pop("value")

    response = client.post("/api/v1/telemetry/inject/", payload, format="json")

    assert response.status_code == 400
    body = response.json()
    assert "errors" in body
    assert body["errors"][0]["loc"] == ["value"]


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_inject_blocked_debug_false_403() -> None:
    baker.make(TelemetryChannel, public_pui="NODE3000005")
    client = APIClient()

    response = client.post("/api/v1/telemetry/inject/", _payload(), format="json")

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_inject_allowed_debug_true_201() -> None:
    baker.make(TelemetryChannel, public_pui="NODE3000005")
    client = APIClient()

    response = client.post("/api/v1/telemetry/inject/", _payload(), format="json")

    assert response.status_code == 201
