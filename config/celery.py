"""
Celery configuration for PeeBot.

This module initializes the Celery application and configures it to work
with Django settings. It auto-discovers tasks from all installed apps.
"""

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

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    "peebot-processor": {
        "task": "apps.event_processors.tasks.run_peebot_processor",
        "schedule": 30.0,  # Run every 30 seconds
    },
}
