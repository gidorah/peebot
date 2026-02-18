from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from apps.telemetry_ingestion.services.enricher import TelemetryEnricher
from apps.telemetry_ingestion.services.validator import LightstreamerReading


class TestTelemetryEnricher:
    def test_enrich_success_standard(self):
        """Test enrichment with a standard timestamp."""
        mock_now = datetime(2026, 6, 1, tzinfo=UTC)

        reading = LightstreamerReading(
            pui="NODE3000005",
            value=Decimal("10.5"),
            timestamp=24.0,
            status_class=None,
            status_indicator=None,
            status_color=None,
        )

        with patch(
            "apps.telemetry_ingestion.services.enricher.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = TelemetryEnricher.enrich(reading)

        assert result["pui"] == "NODE3000005"
        assert result["value"] == Decimal("10.5")
        assert result["timestamp"] == datetime(2026, 1, 1, tzinfo=UTC)

    def test_enrich_rollover_case(self):
        """Test rollover logic: server in Jan 1 receives data from Dec 31."""
        mock_now = datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC)
        hours_from_soy = 8748.0

        reading = LightstreamerReading(
            pui="NODE3000005", Value="10.5", TimeStamp=str(hours_from_soy)
        )

        with patch(
            "apps.telemetry_ingestion.services.enricher.datetime"
        ) as mock_datetime:
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = TelemetryEnricher.enrich(reading)

        expected_ts = (
            datetime(2025, 1, 1, tzinfo=UTC)
            - timedelta(days=1)
            + timedelta(hours=hours_from_soy)
        )
        assert result["timestamp"].year == 2025
        assert result["timestamp"] == expected_ts

    def test_enrich_missing_timestamp(self):
        """Verify it defaults to 'now' if timestamp is missing."""
        reading = LightstreamerReading(pui="NODE3000005", Value="10.5", TimeStamp=None)

        with patch("django.utils.timezone.now") as mock_now_func:
            fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
            mock_now_func.return_value = fixed_now

            result = TelemetryEnricher.enrich(reading)
            assert result["timestamp"] == fixed_now

    def test_enrich_invalid_timestamp_fallback(self):
        """Verify it handles invalid/overflow timestamps by falling back to 'now'."""
        reading = LightstreamerReading(
            pui="NODE3000005",
            Value="10.5",
            TimeStamp=1e18,
        )

        with patch("django.utils.timezone.now") as mock_now_func:
            fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
            mock_now_func.return_value = fixed_now

            result = TelemetryEnricher.enrich(reading)
            assert result["timestamp"] is not None
