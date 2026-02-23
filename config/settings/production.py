"""
Production settings for peebot project.
"""

from .base import *

# DEBUG and ALLOWED_HOSTS are set via environment variables and loaded by base.py

# ==============================================================================
# Security Settings
# ==============================================================================

# SSL is terminated by Traefik — do not redirect here (would cause redirect loops).
SECURE_SSL_REDIRECT = False

# Trust Traefik's X-Forwarded-Proto header to detect HTTPS connections.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# HSTS settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# CSRF trusted origins — required for Django 4.0+ behind reverse proxies.
# Set as a comma-separated list in Coolify UI:
#   CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ==============================================================================
# Middleware (WhiteNoise inserted immediately after SecurityMiddleware)
# ==============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[1:],  # rest of middleware from base.py
]

# ==============================================================================
# Static Files (WhiteNoise — served directly from Gunicorn)
# ==============================================================================

STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ==============================================================================
# Media Files
# ==============================================================================

MEDIA_ROOT = BASE_DIR / "media"

# ==============================================================================
# Email
# ==============================================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# Configure SMTP settings via environment variables.

# ==============================================================================
# Logging (stdout-only — Docker/Coolify captures natively; no Seq, no file handler)
# ==============================================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "()": "django.utils.log.ServerFormatter",
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
