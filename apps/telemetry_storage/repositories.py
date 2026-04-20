"""Repository-pattern data access layer for telemetry storage.

Per ``CLAUDE.md`` Law §2, all database operations on
``TelemetryChannel`` / ``TelemetryReading`` go through a repository
object — consumer modules (ingestion, event processors) do not call the
Django ORM directly. This keeps the storage-layer surface area explicit
and testable.

The module exposes an abstract interface
(:class:`TelemetryRepositoryInterface`) and a Django-backed
implementation (:class:`DjangoTelemetryRepository`). Tests may provide an
in-memory double that implements the same interface.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict

from django.db.models import QuerySet

from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading


class ReadingData(TypedDict, total=False):
    """Typed payload accepted by the repository when creating readings.

    Mirrors the persisted shape of :class:`TelemetryReading` but keeps
    fields optional (``total=False``) because the ingestion pipeline may
    legitimately omit nullable fields (``calibrated_data``, status fields,
    ``metadata``) when the upstream feed does not include them.
    """

    channel: TelemetryChannel
    timestamp: datetime
    value: float | Decimal
    calibrated_data: float | Decimal | None
    status_class: str | None
    status_indicator: str | None
    status_color: str | None
    metadata: dict[str, Any] | None


class TelemetryRepositoryInterface(ABC):
    """Abstract contract for reading and writing telemetry rows.

    Concrete implementations MUST preserve the semantics documented on
    each method so that ingestion and analytics code can be written
    against the interface without branching on backend.
    """

    @abstractmethod
    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        """Return a queryset of non-soft-deleted channels, ordered by PUI."""
        pass

    @abstractmethod
    def get_channel_by_public_pui(self, public_pui: str) -> TelemetryChannel | None:
        """Return the channel with the given ``public_pui``, or ``None``."""
        pass

    @abstractmethod
    async def abulk_create_readings(
        self, readings_data: list[ReadingData]
    ) -> list[TelemetryReading]:
        """Persist a batch of readings asynchronously.

        Implementations MUST swallow duplicate-key conflicts on the
        ``(channel, timestamp)`` unique constraint (ADR-011) rather than
        aborting the whole batch — restart-time snapshot re-broadcasts
        from Lightstreamer rely on this behavior.
        """
        pass

    @abstractmethod
    def create_reading(self, reading_data: ReadingData) -> TelemetryReading:
        """Persist a single reading synchronously.

        Used by the manual-injection debugging endpoint (FR-ING-006); the
        hot-path ingestion pipeline uses :meth:`abulk_create_readings`.
        """
        pass


def get_telemetry_channel_queryset() -> QuerySet[TelemetryChannel]:
    """Return the channel listing queryset used by DRF viewsets.

    Lives at module scope so it can be referenced as a callable from the
    viewset without constructing the repository in the view itself.
    """
    return DjangoTelemetryRepository().get_active_channels()


class DjangoTelemetryRepository(TelemetryRepositoryInterface):
    """Django-ORM-backed implementation of the telemetry repository."""

    def get_active_channels(self) -> QuerySet[TelemetryChannel]:
        """Return active channels ordered by ``public_pui`` for stable paging."""
        return TelemetryChannel.objects.order_by("public_pui")

    def get_channel_by_public_pui(self, public_pui: str) -> TelemetryChannel | None:
        """Return the first channel with the given ``public_pui``, or ``None``."""
        return TelemetryChannel.objects.filter(public_pui=public_pui).first()

    async def abulk_create_readings(
        self, readings_data: list[ReadingData]
    ) -> list[TelemetryReading]:
        """Bulk-insert readings via Django's async ORM with conflict tolerance.

        Uses ``ignore_conflicts=True`` so duplicate ``(channel, timestamp)``
        rows — e.g. Lightstreamer's snapshot re-broadcast immediately after
        service restart — are silently dropped by PostgreSQL's
        ``ON CONFLICT DO NOTHING`` rather than raising ``IntegrityError``
        and aborting the batch (ADR-011).
        """
        readings = [TelemetryReading(**data) for data in readings_data]
        return await TelemetryReading.objects.abulk_create(
            readings, ignore_conflicts=True
        )

    def create_reading(self, reading_data: ReadingData) -> TelemetryReading:
        """Create a single reading row via the synchronous ORM API."""
        return TelemetryReading.objects.create(**reading_data)
