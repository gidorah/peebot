"""
PeeBot Django configuration package.

This ensures that the Celery app is always imported when Django starts
so that the @shared_task decorator will use it.
"""

# Import Celery app to make it available as config.celery
from .celery import app as celery_app

__all__ = ("celery_app",)
