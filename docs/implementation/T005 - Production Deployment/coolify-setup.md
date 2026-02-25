# Coolify Deployment Setup Guide

## Overview

PeeBot is deployed as a Docker Compose stack on a Coolify-managed Hetzner VPS (4 vCPU, 8 GB RAM). Coolify acts as the deployment orchestrator: it clones the repository, builds the Docker image from `docker/prod/Dockerfile`, injects environment variables, and manages the full service lifecycle.

**Architecture summary:**

- Traefik (managed by Coolify) handles TLS termination and domain routing
- Django/Gunicorn runs behind Traefik on port 8000 (the only externally exposed port)
- TimescaleDB, PgBouncer, and Redis are internal-only (no host port mapping)
- All app services (web, worker, beat, ingestion) use the same Docker image — different `command:` per role
- Static files are served by WhiteNoise directly from Gunicorn (no separate file server needed)

Refer to `design.md` for the full architecture, resource allocation, and security rationale.

---

## Prerequisites

Before starting, ensure you have:

- [ ] A Coolify instance with the peebot Git repository connected as a source
- [ ] SSH access to the Hetzner VPS for post-deploy commands (`docker exec`)
- [ ] A Bluesky account with an App Password (optional — required for social posting)
- [ ] An OpenRouter API key (optional — required for joke generation)

---

## Step 1: Create a New Docker Compose Resource in Coolify

1. Open your Coolify dashboard and navigate to the target **Project**.
2. Click **+ New Resource**.
3. Select **Docker Compose** as the resource type.
4. Choose the connected **peebot Git repository** as the source.
5. Select the branch to deploy (typically `main`).

---

## Step 2: Configure the Compose File Path

In the resource settings, set the **Docker Compose file path** to:

```
docker/prod/docker-compose.yml
```

> **Why not the root?** The production compose file lives in `docker/prod/` to keep dev and prod configs separated. Coolify resolves volume paths relative to the compose file location.

---

## Step 3: Configure Environment Variables

Navigate to the **Environment Variables** tab for the resource. Add each variable listed below.

> Variables marked **[COMPOSE]** are already set internally by `docker-compose.yml` using Docker DNS names. Do **not** set them in Coolify — they would override the correct container-network values.

### Django

| Variable | Example Value | Notes |
|----------|--------------|-------|
| `SECRET_KEY` | _(generated)_ | See generation command below. Required. |
| `DEBUG` | `False` | Must be `False` in production. |
| `ALLOWED_HOSTS` | `your-domain.example.com` | Coolify-assigned domain or custom domain. Comma-separated if multiple. |
| `CSRF_TRUSTED_ORIGINS` | `https://your-domain.example.com` | Full `https://` URL. Required for Django 4.0+ behind Traefik. Comma-separated if multiple. |

### Database

| Variable | Example Value | Notes |
|----------|--------------|-------|
| `POSTGRES_DB` | `peebot` | Database name. Must match across all services. |
| `POSTGRES_USER` | `peebot_user` | Application DB user. |
| `POSTGRES_PASSWORD` | _(generated)_ | See password constraints below. Required — no default. |
| `PGBOUNCER_AUTH_PASSWORD` | _(generated)_ | See password constraints below. Required — no default. |

### External APIs (optional but recommended)

| Variable | Example Value | Notes |
|----------|--------------|-------|
| `OPENROUTER_API_KEY` | `sk-or-...` | Required for joke generation. Without it, UPA events are detected but not narrated. |
| `BLUESKY_HANDLE` | `pee-bot.bsky.social` | Required for social posting. |
| `BLUESKY_APP_PASSWORD` | `xxxx-xxxx-xxxx-xxxx` | App Password from Bluesky settings. NOT your account password. |

### Variables to leave unset (handled by compose)

These must **not** be set in Coolify — they are already defined in `docker-compose.yml`:

```
DATABASE_URL               (uses pgbouncer Docker DNS)
CELERY_BROKER_URL          (uses redis Docker DNS)
CELERY_RESULT_BACKEND      (uses redis Docker DNS)
REDIS_URL                  (uses redis Docker DNS)
DJANGO_SETTINGS_MODULE     (set per-service in compose)
```

---

## Step 4: Generate Required Secrets

Run these commands on any machine with OpenSSL available. Use the output as the variable values in Coolify.

```bash
# SECRET_KEY (Django cryptographic signing)
openssl rand -hex 50

# POSTGRES_PASSWORD (PostgreSQL application user)
openssl rand -hex 32

# PGBOUNCER_AUTH_PASSWORD (PgBouncer auth role)
openssl rand -hex 32
```

**Password safety rule:** All generated passwords must use only alphanumeric characters plus `-` and `_`. The `openssl rand -hex` command produces hex output (0-9, a-f) which is always safe.

Do **not** use passwords containing `'`, `@`, `%`, or other special characters — they will break `init-timescale.sh` SQL interpolation and `DATABASE_URL` parsing in the compose file.

---

## Step 5: Set the Bluesky App Password

The `BLUESKY_APP_PASSWORD` in Coolify must be a **Bluesky App Password**, not your account password.

To generate one:

1. Log into [bsky.app](https://bsky.app).
2. Go to **Settings → Privacy and Security → App Passwords**.
3. Click **Add App Password**, name it `peebot-prod`.
4. Copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`) and paste it as `BLUESKY_APP_PASSWORD` in Coolify.

---

## Step 6: Deploy and Verify

### Deploy

1. Click **Deploy** in Coolify to trigger the first build.
2. Coolify will:
   - Clone the repo
   - Build the Docker image from `docker/prod/Dockerfile`
   - Start all 7 services via `docker compose up`
   - Wait for healthchecks to pass

### Verify services are healthy

Check Coolify's service status panel — all services should show **Running / Healthy**:

| Service | Healthcheck |
|---------|------------|
| `timescaledb` | `pg_isready` |
| `pgbouncer` | `pg_isready -p 6432` |
| `redis` | `redis-cli ping` |
| `web` | HTTP GET on port 8000 |

If `timescaledb` fails to start on first deploy, it may need a moment for database initialization. Wait 30–60 seconds and check logs:

```bash
docker logs peebot_timescaledb_prod --tail 30
```

---

## Step 7: First-Time Setup Commands

After all services are healthy, run these commands via SSH on the VPS.

### 7.1 — Run database migrations

```bash
docker exec peebot_web_prod python manage.py migrate
```

Expected output: a list of applied migrations ending with `Applying ...`

### 7.2 — Seed telemetry channels

```bash
docker exec peebot_web_prod python manage.py seed_channels
```

This populates the `TelemetryChannel` table with ISS telemetry channel definitions required for the ingestion pipeline.

### 7.3 — Create admin superuser

```bash
docker exec -it peebot_web_prod python manage.py createsuperuser
```

Follow the prompts to set a username, email, and password. The Django admin is accessible at `https://your-domain/admin/`.

### 7.4 — Verify ingestion is running

```bash
docker logs peebot_ingestion_prod --tail 20
```

Expected output: Lightstreamer connection messages followed by data flow logs at regular intervals.

### 7.5 — Verify Celery worker

```bash
docker logs peebot_worker_prod --tail 20
```

Expected output: Celery task execution logs every 30 seconds (event detection polling).

---

## Redeployment

On subsequent pushes to `main`, Coolify automatically:

1. Detects the new commit (webhook or poll)
2. Rebuilds the Docker image
3. Performs a rolling restart of all app services
4. Infrastructure services (TimescaleDB, PgBouncer, Redis) are not restarted unless their config changes

No manual steps are required for routine code deployments.

For schema changes, run `migrate` manually after the deploy completes:

```bash
docker exec peebot_web_prod python manage.py migrate
```

---

## Useful Justfile Recipes

From any machine with Docker and SSH access to the VPS:

```bash
just prod-build     # Build the production image locally for testing
just prod-migrate   # Run migrations on the running web container
just prod-shell     # Open a Django shell in the web container
just prod-seed      # Re-run seed_channels
just prod-logs      # Follow logs from all production services
```

---

## Troubleshooting

### PgBouncer fails to start

**Symptom:** `peebot_pgbouncer_prod` exits immediately on deploy.

**Cause:** `PGBOUNCER_AUTH_PASSWORD` is not set or is empty in Coolify.

**Fix:** Verify the variable is set in Coolify UI. The PgBouncer entrypoint (`docker/prod/pgbouncer/entrypoint.sh`) validates this at startup and exits with a clear error if missing.

Check logs: `docker logs peebot_pgbouncer_prod`

---

### TimescaleDB init fails with "syntax error at or near ..."

**Symptom:** `peebot_timescaledb_prod` fails on first boot only.

**Cause:** `PGBOUNCER_AUTH_PASSWORD` contains a single quote (`'`) or other SQL-unsafe character.

**Fix:** Regenerate the password using `openssl rand -hex 32` (hex output is always safe). Delete the `peebot_postgres_data_prod` volume and redeploy to re-run init:

```bash
docker volume rm peebot_postgres_data_prod
```

Then redeploy via Coolify.

---

### Static files missing (Django admin has no CSS)

**Symptom:** `/admin/` loads but looks broken (no styling).

**Cause:** `collectstatic` did not run or `STATIC_ROOT` is not correctly served.

**Fix:** The entrypoint script (`docker/prod/entrypoint.sh`) runs `collectstatic --noinput` on every container start. WhiteNoise then serves from `/workspace/staticfiles/`. Check the web container logs for errors during startup:

```bash
docker logs peebot_web_prod --tail 50
```

---

### CSRF verification failed

**Symptom:** Form submissions or admin logins return "CSRF verification failed".

**Cause:** `CSRF_TRUSTED_ORIGINS` does not include the domain being accessed.

**Fix:** Add the full `https://your-domain.example.com` to `CSRF_TRUSTED_ORIGINS` in Coolify UI and redeploy.
