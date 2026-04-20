"""Domain enrichment for validated Lightstreamer readings.

Per ADR-007 (Hybrid Enrichment Strategy), this module owns *domain*
normalization — specifically the conversion of the ISS feed's non-standard
"Hours since start-of-year" timestamp into an aware UTC datetime, including
the New Year's Eve rollover edge case. *System* metadata (``id`` as
UUIDv7, ``created_at``) is left to Django model defaults and is NOT the
responsibility of this module.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.telemetry_ingestion.services.validator import LightstreamerReading

logger = logging.getLogger(__name__)


class TelemetryEnricher:
    """Stateless service that converts validated readings into persistable dicts.

    Used as a pure function on the ingestion consumer loop: given a
    :class:`LightstreamerReading`, return a dict whose keys map directly
    onto :class:`~apps.telemetry_storage.models.TelemetryReading` fields.
    """

    @staticmethod
    def enrich(reading: LightstreamerReading) -> dict[str, Any]:
        """Normalize the reading's timestamp and return a persistable dict.

        The ISS feed encodes time as floating-point "hours since start of
        year (Year-1)". This method converts that to a UTC
        :class:`datetime`, applying a rollover heuristic so that late-year
        samples arriving just after midnight UTC on Jan 1st are attributed
        to the previous year rather than appearing 24h in the future.

        If the reading carries no timestamp or cannot be parsed, the
        enricher falls back to ``timezone.now()`` so downstream persistence
        never receives a ``None`` timestamp.

        Args:
            reading: Validated Lightstreamer reading to enrich.

        Returns:
            A dict with the keys expected by
            :class:`~apps.telemetry_storage.repositories.ReadingData`
            downstream.
        """
        now = datetime.now(tz=UTC)
        reading_ts = None

        if reading.timestamp is not None:
            try:
                hours_from_soy = reading.timestamp
                # Per ADR-007: ISS 'TimeStamp' is Hours from Dec 31 (Year-1).
                # Base date: Dec 31 of the previous year (0.0 hours = Start of Jan 1)
                base_epoch = datetime(now.year, 1, 1, tzinfo=UTC) - timedelta(days=1)
                reading_ts = base_epoch + timedelta(hours=hours_from_soy)

                # Heuristic check for Year Rollover (New Year's Eve)
                # If calculated time is > 24h in the future, it likely belongs
                # to previous year (e.g. processing late Dec 31st data
                # when it is already Jan 1st)
                if reading_ts > now + timedelta(hours=24):
                    base_epoch_prev = datetime(
                        now.year - 1, 1, 1, tzinfo=UTC
                    ) - timedelta(days=1)
                    reading_ts = base_epoch_prev + timedelta(hours=hours_from_soy)
            except (ValueError, TypeError, OverflowError) as e:
                logger.warning(
                    f"Could not parse source timestamp '{reading.timestamp}' "
                    f"for {reading.pui}: {e}. Using now()."
                )

        if reading_ts is None:
            reading_ts = timezone.now()

        return {
            "pui": reading.pui,
            "timestamp": reading_ts,
            "value": reading.value,
            "status_class": reading.status_class,
            "status_indicator": reading.status_indicator,
            "status_color": reading.status_color,
        }
