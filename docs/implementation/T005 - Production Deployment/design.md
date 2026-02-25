# Design: T005 - Production Deployment

## 1. Overview

This document describes the production deployment architecture for PeeBot on a Coolify-managed Hetzner VPS (4 vCPU, 8 GB RAM). The design covers the Docker image build strategy, service composition, resource allocation, networking, logging, security hardening, and the Coolify integration model.

### 1.1 Design Rationale: Why Baked Images?

| Concern | Baked Image (Chosen) | Volume Mount (Rejected) |
|---------|---------------------|------------------------|
| Reproducibility | Image is immutable, tagged, auditable | Runtime depends on host filesystem state |
| Security | No source code on host, smaller attack surface | Full codebase on disk, `.env` files accessible |
| Startup time | Dependencies pre-installed, instant boot | `uv sync` on every container start (~30s) |
| Portability | Same image runs anywhere (CI, staging, prod) | Tied to specific host directory structure |
| Coolify compat | Coolify builds images from Dockerfile naturally | Requires manual host-side setup |

## 2. Production Architecture

```
                   Internet
                      │
                      ▼
              ┌───────────────┐
              │  Coolify       │
              │  Traefik Proxy │  TLS termination, domain routing
              └───────┬───────┘
                      │ :8000
                      ▼
    ┌─────────────────────────────────────────────────────┐
    │              Docker Bridge Network                   │
    │             (peebot_network_prod)                    │
    │                                                     │
    │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
    │  │ Gunicorn  │  │ Celery   │  │ Celery Beat      │  │
    │  │ (web)     │  │ (worker) │  │ (beat)           │  │
    │  │ :8000     │  │          │  │                  │  │
    │  └─────┬─────┘  └────┬─────┘  └────────┬────────┘  │
    │        │             │                  │           │
    │        │    ┌────────┴──────────────────┘           │
    │        │    │                                       │
    │        ▼    ▼                                       │
    │  ┌──────────────┐      ┌─────────────────────────┐ │
    │  │  PgBouncer   │      │  Redis                  │ │
    │  │  :6432       │      │  :6379                  │ │
    │  └──────┬───────┘      │  (AOF, 256MB, LRU)     │ │
    │         │              └─────────────────────────┘ │
    │         ▼                                          │
    │  ┌──────────────┐      ┌─────────────────────────┐ │
    │  │ TimescaleDB  │      │  Ingestion              │ │
    │  │  :5432       │      │  (run_lightstreamer)    │ │
    │  │  (2GB limit) │      │  Lightstreamer → DB     │ │
    │  └──────────────┘      └─────────────────────────┘ │
    │                                                     │
    └─────────────────────────────────────────────────────┘
```

**Key difference from dev:** No Seq, no Flower, no Daphne. Ingestion service added. All ports internal except web:8000.

## 3. Docker Image Design

### 3.1 Multi-Stage Build

```
Stage 1: builder                    Stage 2: runtime
┌──────────────────────────┐       ┌──────────────────────────┐
│ python:3.14-slim          │       │ python:3.14-slim          │
│                          │       │                          │
│ + build-essential        │       │ + libpq5 (runtime only)  │
│ + libpq-dev              │       │                          │
│ + uv (pip install)       │       │ COPY --from=builder      │
│                          │       │   /opt/venv → /opt/venv  │
│ COPY pyproject.toml      │       │                          │
│ COPY uv.lock             │       │ COPY . /workspace        │
│ RUN uv sync --frozen     │  ──▶  │                          │
│   (no --dev)             │       │ USER python (non-root)   │
│                          │       │ ENTRYPOINT entrypoint.sh │
│ /opt/venv populated      │       │ CMD [gunicorn ...]       │
└──────────────────────────┘       └──────────────────────────┘
```

### 3.2 Entrypoint Script

Located at `/usr/local/bin/entrypoint.sh` (avoids being hidden by any volume mount):

1. Run `python manage.py collectstatic --noinput` (idempotent).
2. `exec "$@"` — pass through to CMD (Gunicorn, Celery, or management command).

This pattern allows the same image to serve different roles via different `command:` overrides in the compose file.

### 3.3 Image Reuse

All 4 application services (web, worker, beat, ingestion) use the **same Docker image**. Only the `command:` differs:

| Service   | Command |
|-----------|---------|
| web       | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 ...` |
| worker    | `celery -A config worker --loglevel=info --concurrency=4 ...` |
| beat      | `celery -A config beat --loglevel=info` |
| ingestion | `python manage.py run_lightstreamer` |

## 4. Service Configuration

### 4.1 Resource Allocation (4 vCPU / 8 GB VPS, shared)

| Service     | CPU limit | Mem limit | Mem reservation | Rationale |
|-------------|-----------|-----------|-----------------|-----------|
| timescaledb | 1.5       | 2G        | 1G              | Largest consumer: hypertables, compression, queries |
| pgbouncer   | 0.25      | 256M      | 128M            | Lightweight proxy, minimal footprint |
| redis       | 0.25      | 256M      | 128M            | Celery broker only, 256MB maxmemory |
| web         | 0.5       | 512M      | 256M            | 3 Gunicorn workers (admin UI, light traffic) |
| worker      | 0.5       | 512M      | 256M            | 4 Celery concurrency (event processing, LLM calls) |
| beat        | 0.25      | 256M      | 128M            | Single scheduler process |
| ingestion   | 0.5       | 512M      | 256M            | Async event loop + buffered DB writes |
| **Total**   | **3.75**  | **4.25G** | **2.15G**       | Leaves ~3.75 GB + 0.25 vCPU for OS/Coolify/other |

### 4.2 TimescaleDB Tuning (for 2 GB memory limit)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `shared_buffers` | 512MB | 25% of container memory limit |
| `effective_cache_size` | 1536MB | 75% of container memory limit |
| `work_mem` | 16MB | Reduced from 64MB (fewer concurrent queries) |
| `maintenance_work_mem` | 128MB | Reduced from 512MB (less headroom) |
| `max_connections` | 50 | PgBouncer handles pooling, DB needs fewer direct slots |

**Important:** The `timescale/timescaledb` Docker image (based on the official PostgreSQL image) does **not** read tuning parameters from environment variables like `POSTGRES_SHARED_BUFFERS`. Only standard Docker entrypoint variables (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST_AUTH_METHOD`, `POSTGRES_INITDB_ARGS`) are supported. Custom env var names are silently ignored.

Tuning must be applied via `command:` flags in the compose file:

```yaml
timescaledb:
  image: timescale/timescaledb:latest-pg15
  command: >-
    postgres
    -c shared_buffers=512MB
    -c effective_cache_size=1536MB
    -c work_mem=16MB
    -c maintenance_work_mem=128MB
    -c max_connections=50
```

### 4.3 PgBouncer Tuning (conservative)

| Parameter | Dev | Prod (new) | Rationale |
|-----------|-----|------------|-----------|
| `default_pool_size` | 10 | 10 | Only 3-4 app processes connect |
| `min_pool_size` | 2 | 3 | Keep connections warm |
| `reserve_pool_size` | 3 | 5 | Buffer for burst activity |
| `max_client_conn` | 50 | 50 | Sufficient for 4 services |
| `max_db_connections` | 15 | 20 | Stay well under TimescaleDB's 50 |
| `client_tls_sslmode` | disable | disable | Internal Docker network |
| `server_tls_sslmode` | disable | disable | Internal Docker network |
| `log_connections` | 1 | 0 | Reduce log noise in prod |
| `verbose` | 1 | 0 | Minimal logging |

### 4.3.1 PgBouncer `userlist.txt` Generation (Coolify-compatible)

**Problem:** PgBouncer's `auth_query` mode requires the `pgbouncer_auth` user's password in plaintext in `userlist.txt`. The production `userlist.txt` is gitignored (`**/prod/**/userlist.txt`). When Coolify clones the repo for deployment, the file does not exist, causing PgBouncer to fail on startup.

**Solution:** A custom PgBouncer entrypoint script generates `userlist.txt` at container start from the `PGBOUNCER_AUTH_PASSWORD` environment variable. The `userlist.txt` volume mount is removed entirely.

```bash
# docker/prod/pgbouncer/entrypoint.sh
#!/bin/bash
set -euo pipefail

if [ -z "${PGBOUNCER_AUTH_PASSWORD:-}" ]; then
    echo "FATAL: PGBOUNCER_AUTH_PASSWORD environment variable is required" >&2
    exit 1
fi

# Generate userlist.txt from environment variable (plaintext required for auth_query)
echo "\"pgbouncer_auth\" \"${PGBOUNCER_AUTH_PASSWORD}\"" > /etc/pgbouncer/userlist.txt
chmod 600 /etc/pgbouncer/userlist.txt
echo "Generated /etc/pgbouncer/userlist.txt for pgbouncer_auth user"

# Execute PgBouncer with the provided config
exec pgbouncer "$@"
```

Compose integration:

```yaml
pgbouncer:
  image: edoburu/pgbouncer:v1.24.1-p1
  volumes:
    - ../../docker/prod/pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro
    - ../../docker/prod/pgbouncer/entrypoint.sh:/usr/local/bin/pgbouncer-entrypoint.sh:ro
    # NOTE: userlist.txt is NOT mounted -- generated at runtime by entrypoint
  entrypoint: ["/usr/local/bin/pgbouncer-entrypoint.sh"]
  command: ["/etc/pgbouncer/pgbouncer.ini"]
  environment:
    PGBOUNCER_AUTH_PASSWORD: ${PGBOUNCER_AUTH_PASSWORD}
```

This approach keeps secrets out of git entirely and works with Coolify's clone-and-deploy model.

### 4.4 Gunicorn Configuration

| Parameter | Dev Compose (old) | Prod (new) | Rationale |
|-----------|-------------------|------------|-----------|
| `workers` | 8 | 3 | `2 * CPU_limit + 1` = `2 * 0.5 + 1` (memory-constrained, ~170MB each) |
| `worker-class` | sync | sync | No async views yet |
| `max-requests` | 1000 | 1000 | Prevent memory leaks (worker recycling) |
| `max-requests-jitter` | 100 | 100 | Stagger worker restarts |
| `timeout` | 60 | 60 | |
| `graceful-timeout` | 30 | 30 | |

### 4.5 Redis Configuration

```
redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
```

Reduced from 512MB to 256MB. AOF persistence for Celery result durability across restarts.

### 4.6 Static File Serving (WhiteNoise)

**Problem:** With `DEBUG=False`, Django's `runserver` static file serving is disabled and Gunicorn does not serve static files. Without a solution, the Django admin UI (and any future frontend) will be completely broken — no CSS, no JavaScript.

**Solution:** Use [WhiteNoise](https://whitenoise.readthedocs.io/) to serve static files directly from Gunicorn. WhiteNoise is a WSGI middleware that intercepts requests for static files, serves them with compression and cache-busting, and requires no additional infrastructure (no Nginx, no Traefik path config).

The entrypoint's `collectstatic --noinput` populates `STATIC_ROOT`. WhiteNoise then serves those files at `STATIC_URL` with:
- Automatic gzip + Brotli compression
- Content-hashed filenames for far-future caching
- ETag support

**Production settings additions:**

```python
# config/settings/production.py

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Must be immediately after SecurityMiddleware
    # ... rest of middleware from base.py
]

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

**Dependency:** Add `whitenoise` to `pyproject.toml` production dependencies.

## 5. Security Design

### 5.1 SSL / Proxy Trust

Coolify's Traefik terminates TLS. Django must:

1. Set `SECURE_SSL_REDIRECT = False` (Traefik handles HTTPS redirect).
2. Set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` to trust Traefik's forwarded headers.
3. Keep `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, and HSTS headers (these are correct even behind a proxy).
4. Add `CSRF_TRUSTED_ORIGINS` from an environment variable (required for Django 4.0+ behind reverse proxies).

### 5.2 Network Isolation

```yaml
# Ports exposed to host:
web: 8000        # Traefik proxies to this

# Internal only (no host port mapping):
timescaledb: 5432   # Docker DNS: timescaledb:5432
pgbouncer:   6432   # Docker DNS: pgbouncer:6432
redis:       6379   # Docker DNS: redis:6379
```

### 5.3 Password Management

Three passwords require synchronization:

| Password | Where it's set | Where it's consumed |
|----------|---------------|-------------------|
| `POSTGRES_PASSWORD` | Coolify env vars | TimescaleDB (creates user), PgBouncer (env), compose `DATABASE_URL` |
| `PGBOUNCER_AUTH_PASSWORD` | Coolify env vars | `init-timescale.sh` (creates role), PgBouncer entrypoint (generates `userlist.txt` at runtime) |
| `SECRET_KEY` | Coolify env vars | Django (all crypto operations) |

**Password constraints:** All generated passwords must use URL-safe, shell-safe characters only (alphanumeric, `-`, `_`). Passwords containing single quotes, `@`, `%`, or other special characters will break `DATABASE_URL` composition in the compose file or SQL interpolation in `init-timescale.sh`. Recommended generation command: `openssl rand -hex 32`.

### 5.4 Password Parameterization for init-timescale

**Problem:** PostgreSQL's `docker-entrypoint-initdb.d/` runs `.sql` files directly — no environment variable substitution.

**Solution:** Replace `init-timescale.sql` with `init-timescale.sh`:

```bash
#!/bin/bash
set -euo pipefail

if [ -z "${PGBOUNCER_AUTH_PASSWORD:-}" ]; then
    echo "FATAL: PGBOUNCER_AUTH_PASSWORD environment variable is required" >&2
    exit 1
fi

# Escape single quotes in password for safe SQL interpolation.
# format() with %L handles SQL-level escaping, but the password is first
# expanded by bash into the heredoc, so shell-level escaping is also needed.
ESCAPED_PASSWORD="${PGBOUNCER_AUTH_PASSWORD//\'/\'\'}"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<EOSQL
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgbouncer_auth') THEN
            EXECUTE format('CREATE ROLE pgbouncer_auth WITH LOGIN SUPERUSER PASSWORD %L',
                           '${ESCAPED_PASSWORD}');
        END IF;
    END \$\$;
EOSQL
```

The `.sh` extension tells PostgreSQL's entrypoint to `source` the script as Bash, where env vars are available.

**Safety notes:**
- The `ESCAPED_PASSWORD` variable pre-escapes single quotes (`'` → `''`) before bash expansion into the heredoc, preventing SQL syntax errors.
- The `format() + %L` function then applies proper SQL literal quoting on the already-safe string.
- For maximum safety, generated passwords should be restricted to alphanumeric characters plus `-` and `_` (documented in `.env.production.example`).

## 6. Logging Design

### 6.1 Strategy: Stdout JSON

```
┌─────────────┐     stdout      ┌──────────────┐     Docker      ┌─────────────┐
│ Django App  │────────────────▶│ Docker daemon │────────────────▶│ Coolify UI  │
│ (JSON logs) │                 │ (json-file    │                 │ (log viewer)│
│             │                 │  log driver)  │                 │             │
└─────────────┘                 └──────────────┘                 └─────────────┘
```

### 6.2 Production Logging Configuration

Replace the current `production.py` `LOGGING` dict with:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "django.utils.log.ServerFormatter",
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
```

No Seq, no file handlers, no structlog. Plain Django logging to stdout. Celery and ingestion logs also go to stdout naturally.

## 7. Coolify Integration

### 7.1 Deployment Model

```
GitHub repo (push to main)
        │
        ▼
Coolify detects change (webhook or poll)
        │
        ▼
Coolify clones repo on build server
        │
        ▼
Coolify reads docker/prod/docker-compose.yml
  (configured in project settings as compose file path)
        │
        ▼
Coolify builds image from docker/prod/Dockerfile
  (context: repo root, i.e., ../..)
        │
        ▼
Coolify injects env vars (set in Coolify UI)
        │
        ▼
Coolify starts all services via docker compose up
```

### 7.2 Coolify Project Settings

| Setting | Value |
|---------|-------|
| Source | Connected Git repo (peebot) |
| Build Pack | Docker Compose |
| Compose File | `docker/prod/docker-compose.yml` |
| Environment Variables | Set in Coolify UI (see Section 8) |
| Domain | Coolify-generated or custom (future) |
| Health Check | HTTP GET on web:8000 (Django admin responds) |

### 7.3 Build Context Consideration

Coolify clones the full repo and runs `docker compose` from the repo root. The compose file at `docker/prod/docker-compose.yml` uses `context: ../..` which resolves to the repo root. This is correct for Coolify's clone-and-build workflow.

**Important:** Volume paths like `../../docker/prod/pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro` will also resolve correctly relative to the compose file location, which is how Docker Compose handles relative paths in volume mounts (relative to the compose file, not the build context).

## 8. Environment Variables

### 8.1 Required (set in Coolify UI)

| Variable | Example | Required |
|----------|---------|----------|
| `SECRET_KEY` | `<50+ char random string>` | Yes |
| `DEBUG` | `False` | Yes |
| `ALLOWED_HOSTS` | `<coolify-domain>,localhost` | Yes |
| `CSRF_TRUSTED_ORIGINS` | `https://<coolify-domain>` | Yes |
| `POSTGRES_DB` | `peebot` | Yes |
| `POSTGRES_USER` | `peebot_user` | Yes |
| `POSTGRES_PASSWORD` | `<strong random, 32+ chars>` | Yes |
| `PGBOUNCER_AUTH_PASSWORD` | `<strong random, 32+ chars>` | Yes |
| `OPENROUTER_API_KEY` | `sk-or-...` | For joke generation |
| `BLUESKY_HANDLE` | `pee-bot.bsky.social` | For social posting |
| `BLUESKY_APP_PASSWORD` | `<app password>` | For social posting |

### 8.2 Internal (set in compose `environment:`)

These use Docker DNS names and do not need to be set in Coolify:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@pgbouncer:6432/${POSTGRES_DB}` |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |

## 9. First-Time Deployment Runbook

```
1. Configure env vars in Coolify UI (Section 8.1)
2. Deploy stack via Coolify (triggers build + compose up)
3. Wait for all healthchecks to pass
4. Run migrations:
   docker exec peebot_web_prod python manage.py migrate
5. Seed channels:
   docker exec peebot_web_prod python manage.py seed_channels
6. Create admin user:
   docker exec peebot_web_prod python manage.py createsuperuser
7. Verify ingestion:
   docker logs peebot_ingestion_prod --tail 20
   (should show Lightstreamer connection + data flow)
8. Verify Celery:
   docker logs peebot_worker_prod --tail 20
   (should show task execution every 30s)
```

## 10. Dev vs. Prod Comparison

| Aspect | Dev | Prod |
|--------|-----|------|
| **Image** | Volume-mounted source code | Baked multi-stage image |
| **Web server** | Django `runserver` | Gunicorn (3 workers) |
| **Static files** | Django dev server (auto) | WhiteNoise (compressed, cache-busted) |
| **ASGI** | N/A | N/A (Daphne deferred) |
| **Services** | 8 (+ Seq, Flower) | 7 (+ ingestion, no Seq/Flower/Daphne) |
| **Logging** | Structlog + Rich console + Seq | Plain Django JSON to stdout |
| **TLS** | Disabled | Traefik terminates (Django trusts proxy) |
| **PgBouncer pool** | 10 default / 15 max DB | 10 default / 20 max DB |
| **PgBouncer userlist** | Volume-mounted (dev creds) | Generated at runtime from env var |
| **TimescaleDB RAM** | Uncapped | 2 GB limit |
| **TimescaleDB tuning** | Defaults | `command: postgres -c` flags |
| **Redis** | Ephemeral | AOF persistence, 256MB LRU |
| **Ports exposed** | All (5432, 6432, 6379, 8000, 5341, 5555) | Only 8000 (Traefik proxy) |
| **Env vars** | `.env` file | Coolify UI injection |
| **`uv sync`** | On every container start | Build-time only |
| **User** | UID 1000 (host-mapped) | Non-root `python` user |
