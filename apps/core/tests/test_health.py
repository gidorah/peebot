from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import Client


def test_healthz_returns_200() -> None:
    """
    Verify the /healthz endpoint responds with status 200 and JSON {"status": "ok"}.
    
    Sends a GET request to "/healthz" and asserts the response status code is 200 and the JSON body equals {"status": "ok"}.
    """
    client = Client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


@patch("apps.core.health.sentry_sdk.add_breadcrumb")
@patch("apps.core.health.redis.from_url")
@patch("apps.core.health.connection.cursor")
def test_readyz_returns_503_when_db_down(
    mock_cursor: MagicMock,
    mock_from_url: MagicMock,
    mock_add_breadcrumb: MagicMock,
) -> None:
    """
    Verifies that GET /readyz returns a 503 and records a Sentry breadcrumb when the database health check fails.
    
    Parameters:
        mock_cursor (MagicMock): Fixture mocking the database cursor; configured to raise an error when executing the health query.
        mock_from_url (MagicMock): Fixture mocking redis.from_url and returning a mocked Redis client.
        mock_add_breadcrumb (MagicMock): Fixture mocking sentry_sdk.add_breadcrumb to capture breadcrumb data.
    """
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
            "database": "error",
            "redis": "ok",
        },
    }
    assert "db unavailable" not in response.content.decode()
    mock_add_breadcrumb.assert_called_once_with(
        category="healthcheck",
        message="Readiness check failed",
        level="warning",
        data={
            "path": "/readyz",
            "checks": {
                "database": "error",
                "redis": "ok",
            },
            "failures": {
                "database": {
                    "detail": "db unavailable",
                    "type": "RuntimeError",
                }
            },
        },
    )
    redis_client.ping.assert_called_once_with()


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
            "redis": "error",
        },
    }
    assert "redis unavailable" not in response.content.decode()
    mock_add_breadcrumb.assert_called_once_with(
        category="healthcheck",
        message="Readiness check failed",
        level="warning",
        data={
            "path": "/readyz",
            "checks": {
                "database": "ok",
                "redis": "error",
            },
            "failures": {
                "redis": {
                    "detail": "redis unavailable",
                    "type": "RuntimeError",
                }
            },
        },
    )
    redis_client.close.assert_called_once_with()


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
            "database": "error",
            "redis": "error",
        },
    }
    response_body = response.content.decode()
    assert "db unavailable" not in response_body
    assert "redis unavailable" not in response_body
    mock_add_breadcrumb.assert_called_once_with(
        category="healthcheck",
        message="Readiness check failed",
        level="warning",
        data={
            "path": "/readyz",
            "checks": {
                "database": "error",
                "redis": "error",
            },
            "failures": {
                "database": {
                    "detail": "db unavailable",
                    "type": "RuntimeError",
                },
                "redis": {
                    "detail": "redis unavailable",
                    "type": "RuntimeError",
                },
            },
        },
    )
