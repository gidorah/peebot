import structlog
from django.apps import AppConfig

logger = structlog.get_logger(__name__)


class EventProcessorsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.event_processors"

    def ready(self) -> None:
        """Module initialization."""
        logger.info("event_processors_module_ready")
