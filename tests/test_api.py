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
    """
    Verify the channels list endpoint returns the created telemetry channel in the paginated response.
    
    Creates a TelemetryChannel, performs GET /api/v1/channels/, and asserts the response status is 200, the total count is 1, and the first result's `id` and `public_pui` match the created channel.
    """
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
    assert payload["results"][0]["id"] == channel.id
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
    """
    Verify the events list endpoint returns a successful response containing the created detected event.
    
    Asserts the response status is 200, the paginated count is 1, and the first result's `id` and `event_type` match the created event.
    """
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
    """
    Verify the events API returns detected events ordered by `detected_at` descending.
    
    Creates two DetectedEvent records with different `detected_at` timestamps, requests the events list, and asserts the more recent event appears before the older one.
    """
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
    """
    Verify the channels list endpoint returns paginated results ordered by `public_pui` and provides correct navigation links.
    
    Asserts that when 51 TelemetryChannel records exist:
    - The first page reports a total count of 51, contains 50 results, has a non-null `next` link, and `previous` is null.
    - The first page results are ordered `NODE0001` through `NODE0050`.
    - The second page returns the remaining record (`NODE0051`), has `next` null and a non-null `previous`.
    """
    client = APIClient()

    for index in range(51, 0, -1):
        baker.make(
            TelemetryChannel,
            public_pui=f"NODE{index:04d}",
            description=f"Channel {index}",
            ops_nom=f"OPS {index}",
            eng_nom=f"ENG {index}",
            unit="%",
        )

    response = client.get("/api/v1/channels/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 51
    assert len(payload["results"]) == 50
    assert payload["next"] is not None
    assert payload["previous"] is None
    assert [result["public_pui"] for result in payload["results"]] == [
        f"NODE{index:04d}" for index in range(1, 51)
    ]

    page_2_response = client.get("/api/v1/channels/?page=2")

    assert page_2_response.status_code == 200
    page_2_payload = page_2_response.json()
    assert page_2_payload["count"] == 51
    assert page_2_payload["next"] is None
    assert page_2_payload["previous"] is not None
    assert [result["public_pui"] for result in page_2_payload["results"]] == [
        "NODE0051"
    ]


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
