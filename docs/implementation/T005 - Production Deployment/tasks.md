# Implementation Plan: T005 - Production Deployment

## Phase 1: Production Dockerfile

- [ ] **Step 1**: Write multi-stage production Dockerfile.
    - *File*: `docker/prod/Dockerfile`
    - *Task*: Implement two-stage build:
        - **Stage 1 (builder)**: Base `python:3.14-slim`. Install build deps (`build-essential`, `libpq-dev`). Install `uv` via pip. Copy `pyproject.toml` + `uv.lock`. Run `uv sync --frozen` (without `--dev`) into `/opt/venv`.
        - **Stage 2 (runtime)**: Base `python:3.14-slim`. Install `libpq5` only (runtime C library for psycopg). Copy `/opt/venv` from builder. Copy application source code to `/workspace`. Set `ENV PATH="/opt/venv/bin:$PATH"`. Set `ENV DJANGO_SETTINGS_MODULE=config.settings.production`.
    - *Verification*: `docker build -f docker/prod/Dockerfile -t peebot:test .` succeeds from repo root.

- [ ] **Step 2**: Create non-root user in runtime stage.
    - *File*: `docker/prod/Dockerfile`
    - *Task*: Add `RUN groupadd -g 1000 python && useradd -u 1000 -g python -m python`. Set `RUN chown -R python:python /workspace`. Add `USER python` before ENTRYPOINT.
    - *Verification*: `docker run peebot:test whoami` outputs `python`.

- [ ] **Step 3**: Create entrypoint script.
    - *File*: `docker/prod/entrypoint.sh` (copied to `/usr/local/bin/entrypoint.sh` in Dockerfile)
    - *Task*: Write script that runs `python manage.py collectstatic --noinput` then `exec "$@"`. Mark executable (`chmod +x`). Add `ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]` and `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]` to Dockerfile.
    - *Verification*: `docker run peebot:test` starts Gunicorn and collectstatic runs without error.

- [ ] **Step 4**: Verify `.dockerignore` for production.
    - *File*: `.dockerignore`
    - *Task*: Confirm the following are excluded: `.env`, `.env.local`, `.env.docker`, `.git/`, `docs/`, `_work-tmp/`, `.venv/`, `__pycache__/`, `*.pyc`, `tests/`, `docker/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `celerybeat-schedule*`, `logs/`, `*.md` (except code files). The existing `.dockerignore` (235 lines) is likely comprehensive — review and adjust if needed.
    - *Verification*: Build context size is reasonable (check `docker build` output for context size).

## Phase 2: Production Django Settings

- [ ] **Step 5**: Replace file-based logging with stdout-only.
    - *File*: `config/settings/production.py`
    - *Task*: Replace the entire `LOGGING` dict. Remove the `file` handler. Keep only the `console` handler with `logging.StreamHandler` writing to stdout. Set root logger to `INFO` level. Remove any reference to `logs/django.log`.
    - *Verification*: `DJANGO_SETTINGS_MODULE=config.settings.production python -c "from django.conf import settings; print(settings.LOGGING)"` shows only console handler.

- [ ] **Step 6**: Fix SSL redirect for Traefik proxy.
    - *File*: `config/settings/production.py`
    - *Task*:
        1. Change `SECURE_SSL_REDIRECT = True` to `SECURE_SSL_REDIRECT = False`.
        2. Add `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`.
        3. Keep all other security settings (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS, `X_FRAME_OPTIONS`).
    - *Verification*: Code review confirms no redirect loop risk behind Traefik.

- [ ] **Step 7**: Add `CSRF_TRUSTED_ORIGINS` from environment.
    - *File*: `config/settings/production.py`
    - *Task*: Add `CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])`. This reads a comma-separated list from the env var.
    - *Note*: `env` is already imported from `base.py` via `from .base import *`.
    - *Verification*: Setting is accessible and defaults to empty list when env var is not set.

- [ ] **Step 8**: Verify static files configuration.
    - *File*: `config/settings/production.py`
    - *Task*: Confirm `STATIC_ROOT = BASE_DIR / "staticfiles"` and `STATIC_URL = "/static/"` are set. The entrypoint's `collectstatic` will populate `STATIC_ROOT`. Gunicorn does not serve static files — they're served from the volume or via Traefik/whitenoise (future consideration).
    - *Verification*: `python manage.py collectstatic --noinput --dry-run` shows expected static file collection.

- [ ] **Step 8a**: Add WhiteNoise for production static file serving.
    - *Files*: `pyproject.toml`, `config/settings/production.py`
    - *Task*:
        1. Add `whitenoise` to the `dependencies` list in `pyproject.toml`.
        2. Run `uv lock` to update `uv.lock`.
        3. In `production.py`, insert `WhiteNoiseMiddleware` immediately after `SecurityMiddleware`:
           ```python
           MIDDLEWARE = [
               "django.middleware.security.SecurityMiddleware",
               "whitenoise.middleware.WhiteNoiseMiddleware",
               *[m for m in MIDDLEWARE[1:]],  # rest from base.py
           ]
           ```
           Or explicitly re-list the full middleware stack.
        4. Add the `STORAGES` setting:
           ```python
           STORAGES = {
               "staticfiles": {
                   "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
               },
           }
           ```
    - *Why*: Without WhiteNoise, `DEBUG=False` + Gunicorn means no static files are served. The Django admin UI will be completely broken (no CSS/JS).
    - *Verification*: `python manage.py collectstatic --noinput` succeeds and produces compressed/hashed files in `staticfiles/`. Django admin loads with CSS in a local `DEBUG=False` test.

- [ ] **Step 9**: Remove structlog/Seq from production path.
    - *File*: `config/settings/production.py`
    - *Task*: Confirm `production.py` does NOT add `django_structlog` to `INSTALLED_APPS` or import Seq-related modules. It extends `base.py` which doesn't include them (they're added in `development.py` only). This is a verification step — no changes expected.
    - *Verification*: `INSTALLED_APPS` in production settings does not contain `django_structlog`.

## Phase 3: Parameterize init-timescale

- [ ] **Step 10**: Create shell wrapper for database initialization.
    - *File*: `docker/scripts/init-timescale.sh` (new)
    - *Task*: Write a Bash script that:
        1. Sets `set -euo pipefail` for strict error handling.
        2. Checks that `PGBOUNCER_AUTH_PASSWORD` env var is set (fail fast with clear error if not).
        3. Pre-escapes single quotes in the password (`'` → `''`) before bash expansion into the heredoc to prevent SQL syntax errors.
        4. Runs `psql` as `$POSTGRES_USER` against `$POSTGRES_DB` with inline SQL that:
            - Creates the TimescaleDB extension (`CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE`).
            - Creates the `pgbouncer_auth` role with the escaped password using `format()` + `%L` for SQL-level quoting.
            - Verifies the extension loaded.
        5. Mark executable: `chmod +x`.
    - *Note*: Keep the original `init-timescale.sql` for reference/dev. The prod compose will mount `.sh` instead.
    - *Verification*: Script passes `shellcheck` without errors. Test with a password containing a single quote to confirm escaping works.

- [ ] **Step 11**: Update prod compose to use shell initializer.
    - *File*: `docker/prod/docker-compose.yml` (TimescaleDB service)
    - *Task*:
        1. Change the volume mount from `init-timescale.sql` to `init-timescale.sh`:
           `../../docker/scripts/init-timescale.sh:/docker-entrypoint-initdb.d/01-init-timescale.sh:ro`
        2. Add `PGBOUNCER_AUTH_PASSWORD: ${PGBOUNCER_AUTH_PASSWORD}` to the TimescaleDB environment block.
    - *Verification*: Compose config validation (`docker compose config`) passes.

## Phase 4: PgBouncer Production Config

- [ ] **Step 12**: Disable TLS for internal Docker network.
    - *File*: `docker/prod/pgbouncer/pgbouncer.ini`
    - *Task*: Change `client_tls_sslmode = prefer` to `client_tls_sslmode = disable`. Change `server_tls_sslmode = require` to `server_tls_sslmode = disable`. Add a comment explaining this is safe because all communication is within the Docker bridge network.
    - *Verification*: PgBouncer starts without TLS certificate errors.

- [ ] **Step 13**: Resize connection pools for conservative deployment.
    - *File*: `docker/prod/pgbouncer/pgbouncer.ini`
    - *Task*: Update pool parameters:
        - `default_pool_size = 10` (from 25)
        - `min_pool_size = 3` (from 5)
        - `reserve_pool_size = 5` (from 10)
        - `max_client_conn = 50` (from 200)
        - `max_user_connections = 50` (from 200)
        - `max_db_connections = 20` (from 40)
    - *Verification*: Values are consistent with TimescaleDB's `max_connections = 50`.

- [ ] **Step 14**: Create PgBouncer entrypoint script for runtime `userlist.txt` generation.
    - *File*: `docker/prod/pgbouncer/entrypoint.sh` (new)
    - *Task*: Write a Bash script that:
        1. Sets `set -euo pipefail`.
        2. Validates `PGBOUNCER_AUTH_PASSWORD` is set (exit 1 with clear error if not).
        3. Generates `/etc/pgbouncer/userlist.txt` with the plaintext password: `"pgbouncer_auth" "<password>"`.
        4. Sets file permissions to `600`.
        5. Execs `pgbouncer "$@"` to pass through to the config path.
        6. Mark executable: `chmod +x`.
    - *Why*: The production `userlist.txt` is gitignored (`**/prod/**/userlist.txt`). Coolify clones the repo fresh on each deploy, so the file won't exist. Without it, PgBouncer fails to start. Generating at runtime from env vars is the only Coolify-compatible approach.
    - *Verification*: Script passes `shellcheck`. PgBouncer starts and connects to TimescaleDB.

- [ ] **Step 14a**: Update prod compose to use PgBouncer entrypoint.
    - *File*: `docker/prod/docker-compose.yml` (PgBouncer service)
    - *Task*:
        1. Remove the `userlist.txt` volume mount (`../../docker/prod/pgbouncer/userlist.txt:/etc/pgbouncer/userlist.txt:ro`).
        2. Add the entrypoint volume mount: `../../docker/prod/pgbouncer/entrypoint.sh:/usr/local/bin/pgbouncer-entrypoint.sh:ro`.
        3. Add `entrypoint: ["/usr/local/bin/pgbouncer-entrypoint.sh"]`.
        4. Add `command: ["/etc/pgbouncer/pgbouncer.ini"]`.
        5. Add `PGBOUNCER_AUTH_PASSWORD: ${PGBOUNCER_AUTH_PASSWORD}` to the PgBouncer environment block.
    - *Verification*: `docker compose config` validates. PgBouncer starts with generated userlist.

## Phase 5: Compose Rewrite

- [ ] **Step 15**: Remove source code volume mounts from all app services.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*: Remove `- ../..:/workspace` from `web`, `worker`, `beat` services. Remove `uv_cache` volume from all services. Keep only infrastructure volumes (`static_files`, `media_files` on web).
    - *Verification*: No `../../` workspace mounts remain on app services.

- [ ] **Step 16**: Remove `uv sync` from all runtime commands.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*: Remove `uv sync --frozen &&` prefix from all `command:` directives. Commands become direct process invocations (e.g., `gunicorn config.wsgi:application ...`, `celery -A config worker ...`). Dependencies are already in the image.
    - *Verification*: Each service command starts the process directly without `sh -c` or `uv sync`.

- [ ] **Step 17**: Add ingestion service.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*: Add new service block:
        ```yaml
        ingestion:
          build:
            context: ../..
            dockerfile: docker/prod/Dockerfile
          container_name: peebot_ingestion_prod
          restart: unless-stopped
          command: ["python", "manage.py", "run_lightstreamer"]
          environment:
            DJANGO_SETTINGS_MODULE: config.settings.production
            DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@pgbouncer:6432/${POSTGRES_DB}?application_name=django-ingestion
            CELERY_BROKER_URL: redis://redis:6379/0
            CELERY_RESULT_BACKEND: redis://redis:6379/0
            REDIS_URL: redis://redis:6379/0
          depends_on:
            pgbouncer:
              condition: service_healthy
          deploy:
            resources:
              limits:
                cpus: '0.5'
                memory: 512M
              reservations:
                cpus: '0.25'
                memory: 256M
          networks:
            - peebot_network
        ```
    - *Verification*: `docker compose config` validates successfully.

- [ ] **Step 18**: Remove Daphne service.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*: Delete the entire `daphne:` service block. Remove any port mapping for 8001.
    - *Verification*: No `daphne` service in compose config.

- [ ] **Step 19**: Remove `env_file` directives.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*: Remove `env_file: ../../.env` from all services (`web`, `worker`, `beat`, and newly added `ingestion`). Coolify injects env vars directly into the container environment.
    - *Note*: The `environment:` block with Docker DNS URLs (`pgbouncer:6432`, `redis:6379`) remains — these are internal compose-level values, not secrets.
    - *Verification*: No `env_file` references in compose config.

- [ ] **Step 20**: Resize resource limits and fix TimescaleDB tuning for conservative deployment.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*:
        1. Update all `deploy.resources` blocks per the resource allocation table in design.md Section 4.1.
        2. **Remove** the broken `POSTGRES_SHARED_BUFFERS`, `POSTGRES_EFFECTIVE_CACHE_SIZE`, `POSTGRES_WORK_MEM`, `POSTGRES_MAINTENANCE_WORK_MEM`, and `POSTGRES_MAX_CONNECTIONS` environment variables from the TimescaleDB service. The `timescale/timescaledb` image does not read these — they are silently ignored.
        3. **Add** a `command:` directive to the TimescaleDB service to apply tuning via `-c` flags:
           ```yaml
           command: >-
             postgres
             -c shared_buffers=512MB
             -c effective_cache_size=1536MB
             -c work_mem=16MB
             -c maintenance_work_mem=128MB
             -c max_connections=50
           ```
        4. Update Gunicorn workers from 8 to 3.
        5. Update Redis maxmemory from 512mb to 256mb.
    - *Verification*: Sum of memory limits is ~4.25 GB. Sum of CPU limits is ~3.75. TimescaleDB starts with correct tuning (verify with `SHOW shared_buffers;` via `docker exec`).

- [ ] **Step 21**: Remove external port exposure for infrastructure services.
    - *File*: `docker/prod/docker-compose.yml`
    - *Task*: Remove `ports:` blocks from `timescaledb`, `pgbouncer`, and `redis` services. These are accessible only via Docker DNS within `peebot_network_prod`. Keep `ports: - "8000:8000"` on `web` only.
    - *Verification*: Only port 8000 is mapped to the host.

## Phase 6: Environment Variable Documentation

- [ ] **Step 22**: Create production environment template.
    - *File*: `.env.production.example` (new, at repo root)
    - *Task*: Create a template file documenting all required production environment variables with:
        - Clear section headers (Django, Database, External APIs)
        - Comments explaining each variable's purpose
        - Placeholder values (e.g., `CHANGE-THIS`, `your_key_here`)
        - Generation commands for `SECRET_KEY` and passwords
        - Notes on which vars are set in Coolify UI vs. compose internal
    - *Verification*: File is committed to Git (not in `.gitignore`).

- [ ] **Step 23**: Document Coolify configuration steps.
    - *File*: `docs/implementation/T005 - Production Deployment/coolify-setup.md` (new)
    - *Task*: Step-by-step guide for configuring the Coolify project:
        1. Create new "Docker Compose" resource in Coolify
        2. Connect to the peebot Git repository
        3. Set compose file path to `docker/prod/docker-compose.yml`
        4. Configure environment variables (list each with description)
        5. Generate PgBouncer userlist hash
        6. Deploy and verify
        7. Run first-time setup commands (migrate, seed, superuser)
    - *Verification*: A developer unfamiliar with the project can follow the guide.

## Phase 7: Deployment Pipeline

- [ ] **Step 24**: Add production Justfile recipes.
    - *File*: `Justfile`
    - *Task*: Add recipes:
        ```
        prod-build:     docker build -f docker/prod/Dockerfile -t peebot:local .
        prod-migrate:   docker exec peebot_web_prod python manage.py migrate
        prod-shell:     docker exec -it peebot_web_prod python manage.py shell
        prod-seed:      docker exec peebot_web_prod python manage.py seed_channels
        prod-logs:      docker compose -f docker/prod/docker-compose.yml logs -f
        ```
    - *Verification*: `just --list` shows new recipes.

- [ ] **Step 25**: Document first-time deployment runbook.
    - *File*: `docs/implementation/T005 - Production Deployment/design.md` (Section 9 already contains this)
    - *Task*: Verify the runbook in design.md Section 9 is complete and accurate. No separate file needed — the design doc already covers this.
    - *Verification*: Runbook covers: env var setup, deploy, healthcheck wait, migrate, seed, superuser, ingestion verification, Celery verification.

## Phase 8: Project Documentation Updates

- [ ] **Step 26**: Update project roadmap.
    - *File*: `docs/system-solution/main-tasks.md`
    - *Task*: Add a new section "Phase 4: Production Deployment (T005)" with subtask entries matching Steps 1-25 of this plan.
    - *Verification*: Roadmap reflects T005 as the next major milestone.

- [ ] **Step 27**: Add ADRs to tech-decisions.md.
    - *File*: `docs/system-solution/tech-decisions.md`
    - *Task*: Add three new ADRs:
        - **ADR-012**: Baked Docker Images for Production (multi-stage build, no volume mounts, no runtime `uv sync`).
        - **ADR-013**: Stdout-only Logging in Production (no Seq, no file handlers, Docker-native log capture).
        - **ADR-014**: Coolify Docker Compose Deployment (compose file at `docker/prod/`, env vars via Coolify UI, Traefik TLS termination).
    - *Verification*: ADRs follow the established format (Decision, Status, Context, Rationale, Alternative Rejected).
