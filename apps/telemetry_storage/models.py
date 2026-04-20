"""Database models owned by the telemetry-storage module.

Per ``CLAUDE.md`` Law §1 and ``docs/system-solution/architecture.md`` §6.1,
this module is the single owner of ``TelemetryChannel`` and
``TelemetryReading``. Other modules (``telemetry_ingestion``,
``event_processors``, ``dashboards``) import these models rather than
redefining them.
"""

from django.db import models

from apps.core.models import SoftDeleteModel, TimeStampedModel, UUID7Model


class TelemetryChannel(TimeStampedModel, SoftDeleteModel):
    """Metadata for a single ISS telemetry channel (~400 active total).

    Seeded from ``docs/PUIList.xml`` via the ``seed_channels`` management
    command and kept relatively static thereafter — ADR-005 relies on an
    in-process memory map of ``public_pui → channel`` loaded at ingestion
    startup, so adding or retiring channels currently requires a process
    restart.

    The ``SoftDeleteModel`` mixin is used instead of hard deletes so that
    historical ``TelemetryReading`` rows keep their foreign key target even
    after a channel is retired.
    """

    public_pui = models.CharField(
        max_length=50, unique=True, help_text="Public Program Unique Identifier"
    )
    description = models.CharField(max_length=255)
    ops_nom = models.CharField(max_length=100, help_text="Operations Nomenclature")
    eng_nom = models.CharField(max_length=100, help_text="Engineering Nomenclature")
    unit = models.CharField(max_length=50)

    def __str__(self) -> str:
        return f"{self.public_pui} ({self.ops_nom})"


class TelemetryReading(UUID7Model, TimeStampedModel):
    """A single telemetry sample persisted to the TimescaleDB hypertable.

    The underlying table is converted to a TimescaleDB hypertable by
    project migrations (ADR-003). Migrations also install a compression
    policy (7 days) and a retention policy (30 days) per FR-STO-002 and
    FR-STO-003.

    Deduplication on service restart relies on the composite unique
    constraint ``(channel, timestamp)`` (ADR-011). Batch inserts in the
    ingestion pipeline pass ``ignore_conflicts=True`` so the same
    ``(channel, timestamp)`` pair re-broadcast by Lightstreamer after a
    restart is silently skipped rather than aborting the entire batch.
    """

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
                fields=["channel", "timestamp"], name="unique_channel_timestamp"
            )
        ]
