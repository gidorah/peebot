from __future__ import annotations

from typing import Any

import redis
import sentry_sdk
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

READINESS_CHECK_ERROR = "error"


def _check_database() -> str:
    """
    Verify database connectivity by executing a simple query.
    
    Returns:
        str: "ok" if the database query succeeds.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return "ok"


def _check_redis() -> str:
    """
    Verify connectivity to the Redis broker configured by settings.CELERY_BROKER_URL.
    
    Returns:
        status (str): "ok" if the Redis server accepted a ping.
    """
    client = redis.from_url(settings.CELERY_BROKER_URL)
    try:
        client.ping()
    finally:
        client.close()
    return "ok"


def _build_failure_payload(checks: dict[str, str]) -> dict[str, Any]:
    """
    Builds the JSON payload returned when readiness checks fail.
    
    Parameters:
        checks (dict[str, str]): Mapping of readiness check names to their status values (e.g., "ok" or "error").
    
    Returns:
        dict[str, Any]: Payload with a top-level "status" set to "not_ready" and a "checks" key containing the provided mapping.
    """
    return {
        "status": "not_ready",
        "checks": checks,
    }


def _build_failure_details(exc: Exception) -> dict[str, str]:
    """
    Extract a human-readable detail and exception type name from an Exception.
    
    Parameters:
        exc (Exception): The exception to extract information from.
    
    Returns:
        dict[str, str]: A mapping with keys:
            - "detail": A string describing the exception (exception message or class name).
            - "type": The exception class name.
    """
    error_detail = str(exc) or exc.__class__.__name__
    return {
        "detail": error_detail,
        "type": exc.__class__.__name__,
    }


@require_GET
def healthz(_request: HttpRequest) -> JsonResponse:
    """
    Responds with a minimal liveness JSON indicating the service is operational.
    
    Returns:
        A JsonResponse containing {"status": "ok"}.
    """
    return JsonResponse({"status": "ok"})


@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    """
    Perform readiness checks for external dependencies and return a JSON response describing the results.
    
    Runs the configured readiness checks (database and Redis), collects per-check statuses, and aggregates any failures. If any check fails a Sentry breadcrumb is recorded containing the request path, the checks, and failure details; the view then returns an HTTP 503 response with a payload indicating not-ready status. If all checks succeed the view returns a success payload with the aggregated checks.
    
    Parameters:
        request (HttpRequest): The incoming Django request; its `path` is included in the Sentry breadcrumb when a failure occurs.
    
    Returns:
        JsonResponse: On success, a JSON object {"status": "ready", "checks": {<name>: <status>, ...}}.
                      On failure, a JSON object with status "not_ready" and the `checks` map, returned with HTTP status 503.
    """
    checks: dict[str, str] = {}
    failures: dict[str, dict[str, str]] = {}

    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            checks[name] = check()
        except Exception as exc:  # pragma: no cover - exercised via tests
            checks[name] = READINESS_CHECK_ERROR
            failures[name] = _build_failure_details(exc)

    if failures:
        sentry_sdk.add_breadcrumb(
            category="healthcheck",
            message="Readiness check failed",
            level="warning",
            data={
                "path": request.path,
                "checks": checks,
                "failures": failures,
            },
        )
        return JsonResponse(_build_failure_payload(checks), status=503)

    return JsonResponse({"status": "ready", "checks": checks})
