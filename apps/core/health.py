"""Liveness and readiness HTTP probes for the web process.

Two endpoints are exposed:

* ``/healthz`` — liveness. Confirms the Django process is alive and able to
  respond to requests. Does not check downstream dependencies, so a healthy
  liveness probe means only "the process has not deadlocked."
* ``/readyz`` — readiness. Actively checks PostgreSQL and Redis reachability
  and returns 503 when any dependency is unreachable. Suitable for load
  balancer / Coolify traffic-gating probes.

Both probes are routed at the project URL root (``config/urls.py``).
"""

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
    """Execute a trivial ``SELECT 1`` to verify the database is reachable.

    Returns:
        str: ``"ok"`` on success. Raises any underlying database error on
        failure; ``readyz`` catches and reports it.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return "ok"


READINESS_TIMEOUT_SECONDS = 0.5


def _check_redis() -> str:
    """Ping the Celery broker Redis with a short socket timeout.

    A bounded timeout prevents the readiness probe from stalling the web
    worker when Redis is unreachable — important for fast failover on
    Coolify's Traefik front end.

    Returns:
        str: ``"ok"`` on success. Raises on network/timeout error; ``readyz``
        catches and reports it.
    """
    client = redis.from_url(
        settings.CELERY_BROKER_URL,
        socket_connect_timeout=READINESS_TIMEOUT_SECONDS,
        socket_timeout=READINESS_TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    finally:
        client.close()
    return "ok"


def _build_failure_payload(checks: dict[str, str]) -> dict[str, Any]:
    """Build the JSON body returned when one or more readiness checks fail.

    Args:
        checks: Per-dependency status map (``"ok"`` or ``"error"``).

    Returns:
        A dict serializable to the readiness 503 response body.
    """
    return {
        "status": "not_ready",
        "checks": checks,
    }


def _build_failure_details(exc: Exception) -> dict[str, str]:
    """Extract a short failure summary from an exception for logging.

    Args:
        exc: The exception raised by an individual readiness check.

    Returns:
        A dict with ``detail`` (stringified message or class name fallback)
        and ``type`` (exception class name) for Sentry breadcrumb payloads.
    """
    error_detail = str(exc) or exc.__class__.__name__
    return {
        "detail": error_detail,
        "type": exc.__class__.__name__,
    }


@require_GET
def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness probe — always returns 200 if the web process is responsive.

    Returns:
        JsonResponse: ``{"status": "ok"}`` with HTTP 200.
    """
    return JsonResponse({"status": "ok"})


@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    """Readiness probe — verifies PostgreSQL and Redis reachability.

    Runs every registered dependency check, aggregating results. Failing
    checks are reported as a Sentry breadcrumb (not an exception event —
    readiness failures are expected during rollouts and outages) so the
    next real error has context.

    Args:
        request: The incoming HTTP request. Only used for breadcrumb
            metadata on failure.

    Returns:
        JsonResponse: HTTP 200 with ``{"status": "ready", "checks": ...}``
        when all checks pass; HTTP 503 with ``{"status": "not_ready", ...}``
        when any check fails.
    """
    checks: dict[str, str] = {}
    failures: dict[str, dict[str, str]] = {}

    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            checks[name] = check()
        except Exception as exc:
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
