"""
Development settings for peebot project.
"""

import os

import structlog

from .base import *

# DEBUG is set in .env file and loaded by base.py

# Development-specific apps
INSTALLED_APPS += [
    "django_structlog",
]

# Development-specific middleware
MIDDLEWARE += [
    "django_structlog.middlewares.RequestMiddleware",
]

# Email backend for development (console output)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Django Debug Toolbar configuration (when installed)
INTERNAL_IPS = [
    "127.0.0.1",
]

# Celery configuration for development
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True

# ==============================================================================
# Logging Configuration (Seq + Rich + Structlog)
# ==============================================================================

SEQ_SERVER_URL = env("SEQ_SERVER_URL", default="http://localhost:5341")
SEQ_API_KEY = env("SEQ_API_KEY", default=None)
# Identify who is logging (e.g., 'web', 'worker', 'local')
SERVICE_NAME = os.environ.get("SERVICE_NAME", "peebot-local")

# Structlog Configuration
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # We wrap for formatter so stdlib logging can use it
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


# Custom processor to map standard keys to Seq CLEF keys
def render_to_clef(logger, name, event_dict):
    # Seq expects @t for timestamp, @m for message, @l for level
    event_dict["@m"] = event_dict.pop("event", "")
    event_dict["@l"] = event_dict.pop("level", "info")
    event_dict["@t"] = structlog.processors.TimeStamper(fmt="iso", utc=True)(
        logger, name, {}
    )["timestamp"]

    # Return JSON STRING. This ensures ProcessorFormatter passes a valid JSON string to the handler.
    return structlog.processors.JSONRenderer()(logger, name, event_dict)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "rich": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.dev.ConsoleRenderer(),
        },
        "seq_clef": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": render_to_clef,
        },
    },
    "handlers": {
        "console": {
            "class": "rich.logging.RichHandler",
            "formatter": "rich",
            "rich_tracebacks": True,
            "level": "INFO",  # Changed to INFO to reduce noise, use DEBUG if needed
        },
        "seq": {
            "class": "apps.core.logging.SeqHandler",
            "server_url": SEQ_SERVER_URL,
            "api_key": SEQ_API_KEY,
            "formatter": "seq_clef",
            "level": "INFO",
            "static_fields": {
                "Application": SERVICE_NAME,
                "Environment": "Development",
            },
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "seq"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "seq"],
            "level": "DEBUG",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console", "seq"],
            "level": "INFO",
            "propagate": False,
        },
        # Catch-all for other libraries (like lightstreamer)
        "lightstreamer": {
            "handlers": ["console", "seq"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "seq"],
        "level": "WARNING",
    },
}
