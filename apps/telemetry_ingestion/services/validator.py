"""Hot-path validator for raw Lightstreamer telemetry updates.

Per ADR-004 the ingestion pipeline bypasses DRF serializers for CPU
reasons — at 10k msg/sec bursts, the overhead of instantiating DRF
serializers per message is prohibitive. Pydantic V2 is used instead for
schema validation on the consumer loop. DRF remains in use for the
public REST surface only.
"""

import logging
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class LightstreamerReading(BaseModel):
    """Pydantic schema for a single validated Lightstreamer update.

    Field aliases match the Lightstreamer wire format (``TimeStamp``,
    ``Value``, ``Status.Class`` etc.) while the Python attributes use
    snake_case. ``extra="ignore"`` keeps the parser tolerant of new fields
    the feed may add.
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
    """Validate a raw Lightstreamer field dict into a :class:`LightstreamerReading`.

    Designed to never raise — invalid payloads are logged at ``WARNING`` and
    dropped so a single bad update cannot stall the consumer loop.

    Args:
        pui: The channel identifier (from the Lightstreamer item name).
            Injected into the payload since it is carried separately on
            the subscription message.
        data: The raw changed-fields dict from the Lightstreamer update.

    Returns:
        A validated :class:`LightstreamerReading`, or ``None`` if the
        payload failed schema validation.
    """
    try:
        payload = {**data, "pui": pui}
        return LightstreamerReading.model_validate(payload)
    except ValidationError as e:
        logger.warning(f"Validation failed for {pui}: {e}")
        return None
