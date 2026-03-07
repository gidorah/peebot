from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework.test import APIClient

from apps.event_processors.models import DetectedEvent
from apps.telemetry_storage.models import TelemetryChannel


@pytest.mark.django_db
def test_channels_list_200() -> None:
    channel = baker.make(
        TelemetryChannel,
        public_pui="NODE3000005",
        description="UPA Waste Water Tank Quantity",
        ops_nom="UPA WW TK QTY",
        eng_nom="Node 3 UPA Wastewater Tank",
        unit="%",
    )
    client = APIClient()

    response = client.get("/api/v1/channels/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == str(channel.id)
    assert payload["results"][0]["public_pui"] == "NODE3000005"


@pytest.mark.django_db
def test_channels_list_empty() -> None:
    client = APIClient()

    response = client.get("/api/v1/channels/")

    assert response.status_code == 200
    assert response.json() == {
        "count": 0,
        "next": None,
        "previous": None,
        "results": [],
    }


@pytest.mark.django_db
def test_events_list_200() -> None:
    event = baker.make(
        DetectedEvent,
        event_type="urination",
        channel_id="NODE3000005",
        confidence=Decimal("0.85"),
    )
    client = APIClient()

    response = client.get("/api/v1/events/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == str(event.id)
    assert payload["results"][0]["event_type"] == "urination"


@pytest.mark.django_db
def test_events_ordered_by_detected_at_desc() -> None:
    earlier = timezone.now() - timedelta(minutes=2)
    later = timezone.now() - timedelta(minutes=1)
    baker.make(DetectedEvent, event_type="earlier", detected_at=earlier)
    baker.make(DetectedEvent, event_type="later", detected_at=later)
    client = APIClient()

    response = client.get("/api/v1/events/")

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["event_type"] == "later"
    assert results[1]["event_type"] == "earlier"


@pytest.mark.django_db
def test_channels_pagination() -> None:
    baker.make(TelemetryChannel, _quantity=51)
    client = APIClient()

    response = client.get("/api/v1/channels/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 51
    assert len(payload["results"]) == 50
    assert payload["next"] is not None


@pytest.mark.django_db
def test_openapi_schema_returns_200() -> None:
    client = APIClient()

    response = client.get("/api/schema/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_swagger_ui_returns_200() -> None:
    client = APIClient()

    response = client.get("/api/docs/")

    assert response.status_code == 200
