from django.db import models

from apps.core.models import TimeStampedModel


class TelemetryChannel(TimeStampedModel):
    public_pui = models.CharField(
        max_length=50, unique=True, help_text="Public Program Unique Identifier"
    )
    description = models.CharField(max_length=255)
    ops_nom = models.CharField(max_length=100, help_text="Operations Nomenclature")
    eng_nom = models.CharField(max_length=100, help_text="Engineering Nomenclature")
    unit = models.CharField(max_length=50)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.public_pui} ({self.ops_nom})"
