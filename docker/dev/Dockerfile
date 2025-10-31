FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies for psycopg and compile-time extras
RUN set -eux; \
	apt-get update; \
	apt-get install -y --no-install-recommends build-essential libpq-dev curl; \
	rm -rf /var/lib/apt/lists/*

# Install uv as the package manager/runner
RUN pip install --no-cache-dir uv

WORKDIR /workspace

# Default command can be overridden by docker compose
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
