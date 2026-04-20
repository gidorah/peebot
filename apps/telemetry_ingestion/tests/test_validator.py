"""Tests for the hot-path Pydantic validator (``validate_payload`` + ``LightstreamerReading``)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.telemetry_ingestion.services.validator import (
    LightstreamerReading,
    validate_payload,
)


class TestValidator:
    def test_validate_payload_success_full(self):
        """Verify validation with a complete payload."""
        pui = "NODE3000005"
        data = {
            "Value": "85.5",
            "TimeStamp": "123.456",
            "Status.Class": "Normal",
            "Status.Indicator": "Steady",
            "Status.Color": "Green",
        }

        result = validate_payload(pui, data)

        assert isinstance(result, LightstreamerReading)
        assert result.pui == pui
        assert result.value == Decimal("85.5")
        assert result.timestamp == 123.456
        assert result.status_class == "Normal"
        assert result.status_indicator == "Steady"
        assert result.status_color == "Green"

    def test_validate_payload_success_minimal(self):
        """Verify validation with only required fields."""
        pui = "NODE3000005"
        data = {"Value": "100"}

        result = validate_payload(pui, data)

        assert result is not None
        assert result.pui == pui
        assert result.value == Decimal("100")
        assert result.timestamp is None
        assert result.status_class is None

    def test_validate_payload_missing_value(self):
        """Payload without 'Value' should return None (dropped)."""
        pui = "NODE3000005"
        data = {"TimeStamp": "123.456"}  # Missing Value

        result = validate_payload(pui, data)
        assert result is None

    def test_validate_payload_invalid_value_type(self):
        """Non-numeric value should return None (validation error)."""
        pui = "NODE3000005"
        data = {"Value": "not-a-number"}

        result = validate_payload(pui, data)
        assert result is None

    def test_validate_payload_empty_data(self):
        """Empty data dictionary should return None."""
        result = validate_payload("TEST", {})
        assert result is None

    def test_lightstreamer_reading_direct_validation(self):
        """Test the Pydantic model directly for strictness."""
        # Valid
        reading = LightstreamerReading(pui="TEST", Value="10.5")
        assert reading.value == Decimal("10.5")

        # Invalid value
        with pytest.raises(ValidationError):
            LightstreamerReading(pui="TEST", Value="abc")

        # Missing pui
        with pytest.raises(ValidationError):
            LightstreamerReading(Value="10.5")
