"""Unit tests for config.settings.base._sentry_before_send."""

from typing import Any, cast

from sentry_sdk.types import Event

from config.settings.base import _sentry_before_send


def _make_event(
    *,
    url: str | None = None,
    exception_type: str | None = None,
    exception_module: str | None = None,
    logger: str | None = None,
) -> Event:
    """Build a synthetic Sentry event dict for testing."""
    event: dict[str, Any] = {}
    if url is not None:
        event["request"] = {"url": url}
    if exception_type is not None:
        event["exception"] = {
            "values": [
                {
                    "type": exception_type,
                    "value": "test",
                    **({"module": exception_module} if exception_module else {}),
                }
            ]
        }
    if logger is not None:
        event["logger"] = logger
    return cast(Event, event)


class TestHealthzFilter:
    """Filter /healthz and /readyz endpoint errors."""

    def test_healthz_request_is_filtered(self) -> None:
        """Healthz endpoint events are dropped."""
        event = _make_event(url="http://localhost:8000/healthz")
        assert _sentry_before_send(event, {}) is None

    def test_readyz_request_is_filtered(self) -> None:
        """Readyz endpoint events are dropped."""
        event = _make_event(url="http://localhost:8000/readyz")
        assert _sentry_before_send(event, {}) is None

    def test_other_url_is_not_filtered(self) -> None:
        """Non-health endpoints pass through."""
        event = _make_event(url="http://localhost:8000/api/data")
        assert _sentry_before_send(event, {}) is event

    def test_no_request_is_not_filtered(self) -> None:
        """Events without a request dict pass through."""
        event = _make_event()
        assert _sentry_before_send(event, {}) is event

    def test_request_without_url_is_not_filtered(self) -> None:
        """Request dict missing the url key passes through."""
        event = cast(Event, {"request": {"method": "GET"}})
        assert _sentry_before_send(event, {}) is event


class TestSchedulingErrorFilter:
    """Filter SchedulingError from celery.beat (PEEBOT-10, PEEBOT-11)."""

    def test_scheduling_error_from_celery_beat_is_filtered(self) -> None:
        """SchedulingError from celery.beat logger is dropped."""
        event = _make_event(
            exception_type="SchedulingError",
            logger="celery.beat",
        )
        assert _sentry_before_send(event, {}) is None

    def test_scheduling_error_from_other_logger_is_not_filtered(self) -> None:
        """SchedulingError from a different logger passes through."""
        event = _make_event(
            exception_type="SchedulingError",
            logger="celery.worker",
        )
        assert _sentry_before_send(event, {}) is event

    def test_other_error_from_celery_beat_is_not_filtered(self) -> None:
        """Non-SchedulingError from celery.beat passes through."""
        event = _make_event(
            exception_type="ConnectionError",
            logger="celery.beat",
        )
        assert _sentry_before_send(event, {}) is event


class TestCeleryConsumerLogFilter:
    """Filter Celery consumer log messages (PEEBOT-D, no exception attached)."""

    def test_celery_consumer_log_is_filtered(self) -> None:
        """Log messages from celery.worker.consumer.consumer are dropped."""
        event = cast(Event, {"logger": "celery.worker.consumer.consumer"})
        assert _sentry_before_send(event, {}) is None

    def test_celery_consumer_log_with_logentry_is_filtered(self) -> None:
        """Log messages with logentry from celery.worker.consumer.consumer are dropped."""
        event = cast(
            Event,
            {
                "logger": "celery.worker.consumer.consumer",
                "logentry": {
                    "message": "consumer: Cannot connect to %s: %s.\n%s\n",
                    "formatted": "consumer: Cannot connect to redis://redis:6379/0: ...",
                    "params": ["redis://redis:6379/0", "Error", "Trying again..."],
                },
            },
        )
        assert _sentry_before_send(event, {}) is None

    def test_other_celery_logger_is_not_filtered(self) -> None:
        """Log messages from other celery loggers pass through."""
        event = cast(Event, {"logger": "celery.worker"})
        assert _sentry_before_send(event, {}) is event


class TestKombuOperationalErrorFilter:
    """Filter OperationalError from kombu.exceptions."""

    def test_kombu_operational_error_is_filtered(self) -> None:
        """OperationalError from kombu.exceptions is dropped."""
        event = _make_event(
            exception_type="OperationalError",
            exception_module="kombu.exceptions",
            logger="kombu.connection",
        )
        assert _sentry_before_send(event, {}) is None

    def test_django_db_operational_error_is_not_filtered(self) -> None:
        """OperationalError from django.db passes through (safety check)."""
        event = _make_event(
            exception_type="OperationalError",
            exception_module="django.db",
            logger="django.db.backends",
        )
        assert _sentry_before_send(event, {}) is event

    def test_operational_error_without_module_is_not_filtered(self) -> None:
        """OperationalError with no module info passes through."""
        event = _make_event(
            exception_type="OperationalError",
            logger="kombu.connection",
        )
        assert _sentry_before_send(event, {}) is event

    def test_other_error_from_kombu_is_not_filtered(self) -> None:
        """Non-OperationalError from kombu passes through."""
        event = _make_event(
            exception_type="ConnectionError",
            exception_module="kombu.exceptions",
            logger="kombu.connection",
        )
        assert _sentry_before_send(event, {}) is event


class TestEdgeCases:
    """Boundary conditions for the filter."""

    def test_no_exception_key_is_not_filtered(self) -> None:
        """Events without exception data pass through."""
        event = cast(Event, {"logger": "celery.beat"})
        assert _sentry_before_send(event, {}) is event

    def test_empty_exception_values_is_not_filtered(self) -> None:
        """Events with empty exception values list pass through."""
        event = cast(Event, {"exception": {"values": []}, "logger": "celery.beat"})
        assert _sentry_before_send(event, {}) is event

    def test_exception_values_without_type_is_not_filtered(self) -> None:
        """Events with exception values missing type field pass through."""
        event = cast(
            Event,
            {
                "exception": {"values": [{"value": "test"}]},
                "logger": "celery.beat",
            },
        )
        assert _sentry_before_send(event, {}) is event
