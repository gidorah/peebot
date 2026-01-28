import logging
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class LightstreamerReading(BaseModel):
    """
    Pydantic model for validating raw Lightstreamer telemetry readings.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    pui: str
    value: Decimal = Field(alias="Value")
    timestamp: float | None = Field(None, alias="TimeStamp")
    status_class: str | None = Field(None, alias="Status.Class")
    status_indicator: str | None = Field(None, alias="Status.Indicator")
    status_color: str | None = Field(None, alias="Status.Color")


def validate_payload(pui: str, data: dict[str, Any]) -> LightstreamerReading | None:
    """
    Validates raw incoming dictionary data against a strict schema using Pydantic V2.
    """
    try:
        # We inject 'pui' from the dictionary key (item name)
        payload = {**data, "pui": pui}
        return LightstreamerReading.model_validate(payload)
    except ValidationError as e:
        logger.warning(f"Validation failed for {pui}: {e}")
        return None
