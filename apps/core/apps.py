"""Django ``AppConfig`` for ``apps.core``."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App configuration for the shared ``core`` module.

    ``core`` owns no concrete models — only abstract bases, utilities, and
    infrastructure primitives — so this config is intentionally minimal.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
