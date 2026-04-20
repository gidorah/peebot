"""Django ``AppConfig`` for ``apps.dashboards``."""

from django.apps import AppConfig


class DashboardsConfig(AppConfig):
    """App configuration for the dashboards module.

    The dashboards app is the planned home for PeeBot's real-time web
    interface (per ``docs/system-solution/product-overview.md`` §5 the
    dashboard is currently "Planned — HTMX polling + WebSocket hybrid
    design specified, not yet implemented"). Today the app owns no
    models and carries no views; this config reserves the namespace.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboards"
