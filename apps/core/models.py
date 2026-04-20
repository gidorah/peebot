"""Abstract base models reused across PeeBot's modular apps.

These mixins are owned by ``apps.core`` per the model-ownership rules in
``docs/system-solution/architecture.md`` §6.1 — ``core`` owns abstract base
models only; no concrete tables are defined here. The mixins are imported
into per-app ``models.py`` files wherever they are needed.
"""

import uuid
from typing import Any

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Adds auto-maintained ``created_at`` and ``updated_at`` timestamps.

    ``created_at`` is set once on first save; ``updated_at`` is refreshed on
    every ``save()``. Both use the database-level ``auto_now_add`` /
    ``auto_now`` hooks so the application code never has to set them
    manually.
    """

    created_at = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, auto_now_add=False)

    class Meta:
        abstract = True


class UUID7Model(models.Model):
    """Base model for time-series data requiring UUIDv7 (time-ordered).

    Ideal for TimescaleDB hypertables to ensure index locality. Concrete
    users include ``TelemetryReading``, ``DetectedEvent``, ``SocialPost``,
    and ``ProcessorState``.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
        serialize=False,
    )

    class Meta:
        abstract = True


class ActiveModelManager(models.Manager[Any]):
    """Default manager that hides soft-deleted rows.

    Rows where ``deleted_at`` is non-null are filtered out of the default
    queryset, so ``Model.objects.all()`` only returns active rows. Use the
    ``all_objects`` manager on ``SoftDeleteModel`` to include deleted rows.
    """

    def get_queryset(self) -> models.QuerySet[Any]:
        """Return a queryset limited to rows where ``deleted_at`` is NULL."""
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    """Adds soft-delete semantics via a nullable ``deleted_at`` timestamp.

    Attributes:
        deleted_at: Timestamp of soft deletion, or ``None`` for active rows.
        objects: Manager that hides soft-deleted rows by default.
        all_objects: Unfiltered manager including soft-deleted rows.
    """

    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveModelManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        """Mark this record as deleted by stamping ``deleted_at`` with ``now()``.

        Persists only the ``deleted_at`` column. The row remains in the
        database but is filtered out of the default manager's querysets.
        """
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self) -> None:
        """Undo a soft delete by clearing ``deleted_at``.

        Persists only the ``deleted_at`` column.
        """
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_active(self) -> bool:
        """Return ``True`` when the row has not been soft-deleted."""
        return self.deleted_at is None

    @property
    def is_deleted(self) -> bool:
        """Return ``True`` when the row has been soft-deleted."""
        return self.deleted_at is not None
