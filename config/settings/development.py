"""
Development settings for peebot project.
"""

from .base import *

# DEBUG is set in .env file and loaded by base.py

# Development-specific apps
INSTALLED_APPS += [
    # Add development tools here, e.g.:
    # 'debug_toolbar',
]

# Development-specific middleware
MIDDLEWARE += [
    # Add development middleware here, e.g.:
    # 'debug_toolbar.middleware.DebugToolbarMiddleware',
]

# Email backend for development (console output)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Development database configuration (will be updated to TimescaleDB later)
# Currently using the default SQLite from base.py

# Django Debug Toolbar configuration (when installed)
INTERNAL_IPS = [
    '127.0.0.1',
]

# Celery configuration for development
CELERY_TASK_ALWAYS_EAGER = False  # Set to True to run tasks synchronously in tests
CELERY_TASK_EAGER_PROPAGATES = True
