"""Testing settings for peebot project.

Used by pytest to run tests with direct database access (bypasses PgBouncer).
"""

from .development import *

# Override database to use direct TimescaleDB connection for test database creation
# PgBouncer doesn't allow creating new databases dynamically
TEST_DATABASE_URL = env("TEST_DATABASE_URL", default=None)
if TEST_DATABASE_URL:
    DATABASES = {"default": env.db_url("TEST_DATABASE_URL")}

# Disable Seq logging during tests to reduce noise
LOGGING["handlers"]["seq"]["level"] = "CRITICAL"

# Speed up password hashing for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
