import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from django.utils import timezone

from apps.telemetry_ingestion.services.validator import LightstreamerReading

logger = logging.getLogger(__name__)


class TelemetryEnricher:
    """
    Service for enriching validated telemetry data with normalized timestamps
     and other domain-specific logic.
    """

    @staticmethod
    def enrich(reading: LightstreamerReading) -> dict[str, Any]:
        """
        Transforms a LightstreamerReading into an enriched dictionary ready for persistence.
        """
        now = datetime.now(tz=UTC)
        reading_ts = None

        if reading.timestamp is not None:
            try:
                hours_from_soy = reading.timestamp
                # ADR-010: ISS 'TimeStamp' is Hours from Dec 31 (Year-1).
                # Base date: Dec 31 of the previous year (0.0 hours = Start of Jan 1)
                base_epoch = datetime(now.year, 1, 1, tzinfo=UTC) - timedelta(days=1)
                reading_ts = base_epoch + timedelta(hours=hours_from_soy)

                # Heuristic check for Year Rollover (New Year's Eve)
                # If calculated time is > 24h in the future, it likely belongs to previous year
                # (e.g. processing late Dec 31st data when it is already Jan 1st)
                if reading_ts > now + timedelta(hours=24):
                    base_epoch_prev = datetime(
                        now.year - 1, 1, 1, tzinfo=UTC
                    ) - timedelta(days=1)
                    reading_ts = base_epoch_prev + timedelta(hours=hours_from_soy)
            except (ValueError, TypeError, OverflowError) as e:
                logger.warning(
                    f"Could not parse source timestamp '{reading.timestamp}' for {reading.pui}: {e}. Using now()."
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
