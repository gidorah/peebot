from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel, UUID7Model


class TelemetryChannel(TimeStampedModel, SoftDeleteModel):
    public_pui = models.CharField(
        max_length=50, unique=True, help_text="Public Program Unique Identifier"
    )
    description = models.CharField(max_length=255)
    ops_nom = models.CharField(max_length=100, help_text="Operations Nomenclature")
    eng_nom = models.CharField(max_length=100, help_text="Engineering Nomenclature")
    unit = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.public_pui} ({self.ops_nom})"


class TelemetryReading(UUID7Model, TimeStampedModel, SoftDeleteModel):
    channel = models.ForeignKey(
        TelemetryChannel, on_delete=models.CASCADE, related_name="readings"
    )
    timestamp = models.DateTimeField(db_index=True)
    value = models.DecimalField(max_digits=20, decimal_places=10)
    calibrated_data = models.DecimalField(
        max_digits=20, decimal_places=10, null=True, blank=True
    )
    status_class = models.CharField(max_length=50, null=True, blank=True)
    status_indicator = models.CharField(max_length=50, null=True, blank=True)
    status_color = models.CharField(max_length=50, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["channel", "-timestamp"]),
            models.Index(fields=["created_at", "timestamp"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["id", "timestamp"], name="unique_id_timestamp"
            )
        ]
