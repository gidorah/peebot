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
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return "ok"


def _check_redis() -> str:
    client = redis.from_url(settings.CELERY_BROKER_URL)
    try:
        client.ping()
    finally:
        client.close()
    return "ok"


def _build_failure_payload(checks: dict[str, str]) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "checks": checks,
    }


def _build_failure_details(exc: Exception) -> dict[str, str]:
    error_detail = str(exc) or exc.__class__.__name__
    return {
        "detail": error_detail,
        "type": exc.__class__.__name__,
    }


@require_GET
def healthz(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
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
