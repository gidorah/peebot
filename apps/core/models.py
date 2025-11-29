from uuid import uuid4

from django.db import models
from django.db.models.fields import DateTimeField, UUIDField
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at: DateTimeField = DateTimeField(auto_now=False, auto_now_add=True)
    updated_at: DateTimeField = DateTimeField(auto_now=True, auto_now_add=False)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    id: UUIDField = UUIDField(primary_key=True, default=uuid4, editable=False)

    class Meta:
        abstract = True


class ActiveModelManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    deleted_at: DateTimeField | None = DateTimeField(null=True, blank=True)

    objects = ActiveModelManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self) -> None:
        self.deleted_at: timezone.datetime = timezone.now()
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
