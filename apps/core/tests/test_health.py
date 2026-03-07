from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_returns_200() -> None:
    client = Client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
@patch("apps.core.health.redis.from_url")
@patch("apps.core.health.connection.cursor")
def test_readyz_returns_200_when_healthy(
    mock_cursor: MagicMock,
    mock_from_url: MagicMock,
) -> None:
    client = Client()
    redis_client = MagicMock()
    mock_from_url.return_value = redis_client

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }
    mock_cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
        "SELECT 1"
    )
    redis_client.ping.assert_called_once_with()
    redis_client.close.assert_called_once_with()


@pytest.mark.django_db
@patch("apps.core.health.sentry_sdk.add_breadcrumb")
@patch("apps.core.health.redis.from_url")
@patch("apps.core.health.connection.cursor")
def test_readyz_returns_503_when_db_down(
    mock_cursor: MagicMock,
    mock_from_url: MagicMock,
    mock_add_breadcrumb: MagicMock,
) -> None:
    client = Client()
    redis_client = MagicMock()
    mock_from_url.return_value = redis_client
    mock_cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError(
        "db unavailable"
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": "error: db unavailable",
            "redis": "ok",
        },
    }
    mock_add_breadcrumb.assert_called_once()
    redis_client.ping.assert_called_once_with()


@pytest.mark.django_db
@patch("apps.core.health.sentry_sdk.add_breadcrumb")
@patch("apps.core.health.redis.from_url")
@patch("apps.core.health.connection.cursor")
def test_readyz_returns_503_when_redis_down(
    mock_cursor: MagicMock,
    mock_from_url: MagicMock,
    mock_add_breadcrumb: MagicMock,
) -> None:
    client = Client()
    redis_client = MagicMock()
    redis_client.ping.side_effect = RuntimeError("redis unavailable")
    mock_from_url.return_value = redis_client

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": "ok",
            "redis": "error: redis unavailable",
        },
    }
    mock_add_breadcrumb.assert_called_once()
    redis_client.close.assert_called_once_with()


@pytest.mark.django_db
@patch("apps.core.health.sentry_sdk.add_breadcrumb")
@patch("apps.core.health.redis.from_url")
@patch("apps.core.health.connection.cursor")
def test_readyz_reports_both_failures(
    mock_cursor: MagicMock,
    mock_from_url: MagicMock,
    mock_add_breadcrumb: MagicMock,
) -> None:
    client = Client()
    redis_client = MagicMock()
    redis_client.ping.side_effect = RuntimeError("redis unavailable")
    mock_from_url.return_value = redis_client
    mock_cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError(
        "db unavailable"
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": "error: db unavailable",
            "redis": "error: redis unavailable",
        },
    }
    mock_add_breadcrumb.assert_called_once()
