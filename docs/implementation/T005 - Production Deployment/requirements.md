# Requirements: T005 - Production Deployment

## 1. Goal

Deploy the PeeBot modular monolith to a Coolify-managed Hetzner VPS (4 vCPU, 8 GB RAM) as a Docker Compose stack, with production-grade containerization, security, logging, and resource management.

## 2. Background

The development environment is fully functional: 8 Docker services (TimescaleDB, PgBouncer, Redis, Seq, Django web, Celery worker, Celery beat, Flower, and ingestion) run via `docker/dev/docker-compose.yml`. A production compose file and directory structure exist at `docker/prod/` but are incomplete:

1. **Production Dockerfile is empty** — no image can be built.
2. **Ingestion service is missing** from the prod compose — the core data pipeline has no entry.
3. **Volume mounts** (`../../:/workspace`) in prod compose are a dev pattern — source code should be baked into the image.
4. **`init-timescale.sql`** has a hardcoded `pgbouncer_auth` password.
5. **`production.py`** logs to files inside the container and lacks structured logging.
6. **`SECURE_SSL_REDIRECT = True`** will cause redirect loops behind Coolify's Traefik proxy.
7. **Resource limits** are sized for a dedicated 8-core/32GB server, not a shared 4vCPU/8GB VPS.
8. **Infrastructure ports** (5432, 6379, 6432) are exposed externally.
9. **No `collectstatic`** or migration step in the deployment pipeline.
10. **Daphne service** is included but the dashboards module is empty (no ASGI consumers).

## 3. Functional Requirements

### 3.1 Docker Image (FR-DEPLOY-001)

1. The system shall build a multi-stage production Docker image that bakes all application code and dependencies at build time.
2. The image shall not require `uv sync` at runtime.
3. The image shall run as a non-root user.
4. The image shall execute `collectstatic --noinput` at container start via an entrypoint script.
5. The entrypoint script shall be placed at `/usr/local/bin/entrypoint.sh` to avoid being hidden by volume mounts.

### 3.2 Service Composition (FR-DEPLOY-002)

1. The production stack shall consist of 7 services: TimescaleDB, PgBouncer, Redis, Django web (Gunicorn), Celery worker, Celery beat, and ingestion (Lightstreamer).
2. The ingestion service shall run `manage.py run_lightstreamer` using the same image as the web service.
3. Daphne shall not be included until the dashboards module has functional WebSocket consumers.
4. Flower and Seq shall not be included (dev-only tooling).
5. PgBouncer shall use a custom entrypoint script that generates `userlist.txt` at container start from the `PGBOUNCER_AUTH_PASSWORD` environment variable. The `userlist.txt` file shall not be committed to git or volume-mounted.

### 3.2.1 Static File Serving (FR-DEPLOY-002.1)

1. The production stack shall use WhiteNoise to serve static files directly from Gunicorn, eliminating the need for a separate static file server or Traefik path configuration.
2. WhiteNoise shall be added as a production dependency in `pyproject.toml`.
3. `WhiteNoiseMiddleware` shall be added to production Django middleware immediately after `SecurityMiddleware`.
4. The `STORAGES` setting shall use `whitenoise.storage.CompressedManifestStaticFilesStorage` for automatic compression and cache-busting.

### 3.3 Environment Configuration (FR-DEPLOY-003)

1. The system shall not use `env_file` directives in the compose file. Coolify shall inject environment variables via its UI.
2. Internal service URLs (`DATABASE_URL`, `CELERY_BROKER_URL`, `REDIS_URL`) shall use Docker DNS names (e.g., `pgbouncer`, `redis`).
3. A `.env.production.example` template shall document all required production environment variables.

### 3.4 Database Initialization (FR-DEPLOY-004)

1. The `pgbouncer_auth` password in `init-timescale.sql` shall be parameterized via the `PGBOUNCER_AUTH_PASSWORD` environment variable.
2. The initialization shall use a shell wrapper script (`init-timescale.sh`) to template SQL with `envsubst` before execution.
3. The `PGBOUNCER_AUTH_PASSWORD` variable shall be passed to the TimescaleDB container's environment.
4. Generated passwords (e.g., `POSTGRES_PASSWORD`, `PGBOUNCER_AUTH_PASSWORD`) shall be restricted to URL-safe, shell-safe characters (alphanumeric, `-`, `_`). Passwords containing single quotes, `@`, `%`, or other special characters may break SQL interpolation in `init-timescale.sh` or `DATABASE_URL` composition. This constraint shall be documented in `.env.production.example`.
5. TimescaleDB performance tuning parameters (`shared_buffers`, `effective_cache_size`, `work_mem`, etc.) shall be applied via `command:` flags (`postgres -c key=value`) in the compose file, not via `POSTGRES_*` environment variables (the `timescale/timescaledb` image does not read tuning-related env vars).

### 3.5 First-Time Deployment (FR-DEPLOY-005)

1. The deployment process shall support a documented first-time setup sequence: deploy stack, run migrations, seed channels, create superuser.
2. Migrations shall be runnable via `docker exec` against the running web container.

## 4. Non-Functional Requirements

### 4.1 Security (NFR-DEPLOY-001)

1. No production passwords shall have default values. `POSTGRES_PASSWORD` and `PGBOUNCER_AUTH_PASSWORD` shall be required (no fallback).
2. Infrastructure ports (TimescaleDB 5432, PgBouncer 6432, Redis 6379) shall not be exposed to the host. Only `web:8000` shall be externally accessible (Traefik proxies to it).
3. `SECURE_SSL_REDIRECT` shall be `False` — Coolify's Traefik handles TLS termination.
4. `SECURE_PROXY_SSL_HEADER` shall be set to trust Traefik's `X-Forwarded-Proto` header.
5. `CSRF_TRUSTED_ORIGINS` shall be configurable via environment variable.
6. PgBouncer's `userlist.txt` shall not be committed to version control. The PgBouncer entrypoint script shall generate it at runtime from the `PGBOUNCER_AUTH_PASSWORD` environment variable, eliminating the need for a gitignored secret file that breaks Coolify's clone-and-deploy workflow.

### 4.2 Resource Management (NFR-DEPLOY-002)

1. Total resource allocation shall not exceed ~4 GB RAM and ~3.75 vCPU, leaving headroom for the OS, Coolify agent, and other light services on the VPS.
2. All services shall have explicit `deploy.resources.limits` and `reservations`.
3. TimescaleDB tuning parameters (`shared_buffers`, `effective_cache_size`, `work_mem`) shall be sized for a 2 GB memory limit.
4. Gunicorn workers shall be reduced to 2-3 (memory-constrained environment).

### 4.3 Logging (NFR-DEPLOY-003)

1. All application logs shall be written to stdout/stderr in plain JSON format.
2. File-based logging (`logs/django.log`) shall be removed from production settings.
3. Docker/Coolify shall capture logs natively from container stdout.

### 4.4 Reliability (NFR-DEPLOY-004)

1. All services shall use `restart: unless-stopped`.
2. Infrastructure services (TimescaleDB, PgBouncer, Redis) shall have healthchecks.
3. Application services shall depend on infrastructure healthchecks before starting.
4. Redis shall use AOF persistence to survive container restarts.

### 4.5 Networking (NFR-DEPLOY-005)

1. PgBouncer TLS shall be disabled for internal Docker network communication (both `client_tls_sslmode` and `server_tls_sslmode`).
2. All services shall communicate over a single bridge network (`peebot_network_prod`).

## 5. Constraints

1. The VPS is shared with other light services managed by Coolify (C-001).
2. Coolify deploys via Docker Compose — the compose file path is configured in the Coolify project settings (C-002).
3. The compose file shall remain at `docker/prod/docker-compose.yml` (C-003).
4. No Kubernetes, Swarm, or orchestration beyond Docker Compose (C-004).
5. Coolify handles TLS termination, domain routing, and reverse proxying via Traefik (C-005).

## 6. Assumptions

1. The Coolify instance is already connected to the peebot Git repository (A-001).
2. The Hetzner VPS has Docker and the Coolify agent installed (A-002).
3. No custom domain is configured initially; Coolify's auto-generated domain or IP will be used (A-003).
4. The Bluesky and OpenRouter API credentials from development can be reused in production (A-004).
