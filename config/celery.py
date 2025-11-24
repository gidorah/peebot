"""
Celery configuration for PeeBot.

This module initializes the Celery application and configures it to work
with Django settings. It auto-discovers tasks from all installed apps.
"""

from typing import Any
import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

# Create the Celery app instance
app = Celery("peebot")

# Load configuration from Django settings, using the CELERY namespace
# This means all Celery config options must be prefixed with CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed Django apps
# This will look for tasks.py files in each app
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self: Any) -> None:
    """Debug task to test Celery is working correctly."""
    print(f"Request: {self.request!r}")
