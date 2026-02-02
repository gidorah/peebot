import uuid
from typing import Any

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now=False, auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, auto_now_add=False)

    class Meta:
        abstract = True


class UUID7Model(models.Model):
    """
    Base model for Time-Series data requiring UUIDv7 (time-ordered).
    Ideal for TimescaleDB Hypertables to ensure index locality.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,  # type: ignore[attr-defined]
        editable=False,
        serialize=False,
    )

    class Meta:
        abstract = True


class ActiveModelManager(models.Manager[Any]):
    def get_queryset(self) -> models.QuerySet[Any]:
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveModelManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
