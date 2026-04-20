"""Project-level URL configuration for the PeeBot Django app.

Routes mounted here:

* ``/healthz``, ``/readyz`` — operational probes (see :mod:`apps.core.health`).
* ``/api/v1/`` — versioned public REST API (see :mod:`config.api_urls`).
* ``/api/schema/``, ``/api/docs/`` — OpenAPI schema and Swagger UI.
* ``/admin/`` — Django admin.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from apps.core.health import healthz, readyz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("api/v1/", include("config.api_urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema", permission_classes=[AllowAny]
        ),
        name="swagger-ui",
    ),
    path("admin/", admin.site.urls),
]
