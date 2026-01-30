"""Event processors package - analytics modules for pattern detection."""

from apps.event_processors.processors.base import BaseProcessor, DetectionResult
from apps.event_processors.processors.pee_bot import PeeBotProcessor

__all__ = ["BaseProcessor", "DetectionResult", "PeeBotProcessor"]
