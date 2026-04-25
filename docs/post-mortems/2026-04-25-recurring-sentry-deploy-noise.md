# Post-Mortem: Recurring Sentry Deploy-Noise Issues (PEEBOT-D, E, F, C, 10, 11)

**Date:** 2026-04-25
**Author:** Onur Akyüz
**Status:** Resolved
**Severity:** Low (noise, not user-facing outages)
**Duration:** ~5 weeks (2026-03-19 to 2026-04-25)

---

## Executive Summary

Despite multiple incremental fixes, Sentry continued to surface the same deploy-restart errors after every deployment. A multi-agent investigation revealed that the root cause was not code defects, but **infrastructure-level container recreation** combined with **inadequate Sentry filtering** and **missing graceful shutdown configuration**. The final resolution required changes across three layers: Sentry filtering logic, Docker Compose deployment configuration, and stale environment cleanup.

---

## Timeline

| Date | Event |
|------|-------|
| **2026-03-19** | First PEEBOT-D events appear (Kombu consumer Redis DNS failures) |
| **2026-03-20** | PR #105: Add Redis readiness loop to entrypoint; `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True` |
| **2026-04-14** | PR #143: Add Sentry `before_send` filters for `SchedulingError` and `kombu.exceptions.OperationalError`; add worker healthcheck |
| **2026-04-16** | Issues #139 (PEEBOT-F) and #140 (PEEBOT-C) opened — problems persist |
| **2026-04-20** | PR #141: Docstring sweep (unrelated, but touched same files) |
| **2026-04-22** | Issue #142 opened (PEEBOT-10/11) |
| **2026-04-24 22:00** | PR #144 merged: Fix PEEBOT-D filter (logger check before exception check) |
| **2026-04-24 22:04** | **Last PEEBOT-E event** — PR #145 (PEEBOT-E fix) not yet merged |
| **2026-04-25 09:57** | PR #145 merged: Add PEEBOT-E filter for ingestion flush_buffer |
| **2026-04-25 09:59** | **PEEBOT-D and PEEBOT-F events still appear** — 2 minutes after PR #145 deploy |
| **2026-04-25 10:00** | Server investigation begins: old PR preview containers found running (pr-104, pr-105) |
| **2026-04-25 12:24** | PR #146 merged: Fix PEEBOT-D structural bug, add PEEBOT-F filter, add `stop_grace_period`, fix ALLOWED_HOSTS |
| **2026-04-25 12:25+** | **Zero new Sentry events** after deploy — issue confirmed resolved |

---

## Affected Issues

| Sentry ID | GitHub Issue | Title | Root Cause |
|-----------|--------------|-------|------------|
| PEEBOT-D | #125 | Kombu consumer Redis reconnect ERROR | Unfiltered log-message events from `celery.worker.consumer.consumer` |
| PEEBOT-E | #127 | Postgres server-close during Lightstreamer flush | `exc_info=True` on WARNING log captured by Sentry LoggingIntegration |
| PEEBOT-F | #139 | PgBouncer connection refused exhausting retries | Terminal `psycopg.OperationalError` from deploy-restart window |
| PEEBOT-C | #140 | DNS resolution failure exhausting retries | Transient DNS blip during container restart |
| PEEBOT-10 | #142 | SchedulingError: Redis connection refused | Beat attempting to schedule before Redis DNS ready |
| PEEBOT-11 | #142 | SchedulingError: Redis DNS failure | Same as PEEBOT-10 |

---

## Root Cause Analysis

### Primary Cause: Docker Container Recreation (Not Rolling Restart)

The production `docker-compose.yml` had **no zero-downtime primitives**:
- No `deploy.update_config` with `order: start-first`
- No `stop_grace_period` (default 10s → SIGKILL)
- No healthchecks on `beat` and `ingestion` services

On every Coolify deploy, old containers were **stopped before new ones started**, severing all Redis/PgBouncer connections. Active Kombu heartbeats and DB queries failed mid-flight, producing ERROR-level logs that Sentry captured.

### Secondary Cause: Sentry Filter Gaps

The `_sentry_before_send` function had two structural problems:

1. **PEEBOT-D bypass**: `logger_name` was extracted **after** `if not exception: return event`. PEEBOT-D events are pure log messages (no exception field), so they bypassed the filter entirely.

2. **PEEBOT-F missing**: No filter existed for `psycopg.OperationalError` from `run_peebot_processor` — a terminal retry-exhaustion failure that only occurs during deploy windows.

### Contributing Cause: Stale PR Preview Deployments

Two 5-week-old PR preview deployments (`pr-104`, `pr-105`) were still running on the same Docker network as production. This caused:
- Broken worker healthchecks (`celery inspect ping` contacted phantom workers)
- Potential DNS confusion (3 Redis instances, 3 PgBouncer instances on same network)
- Resource waste (~20 extra containers)

### Contributing Cause: Broken Web Healthcheck

`ALLOWED_HOSTS` rejected `localhost`, causing the web container healthcheck to fail with HTTP 400. This made it impossible to verify web service health during deploys.

---

## Impact

- **Sentry noise**: 6 recurring issues, ~50+ events over 5 weeks
- **Alert fatigue**: Every deploy triggered new Sentry events, masking genuine issues
- **No user impact**: All errors were transient and self-recovering; no data loss or service degradation
- **Operational cost**: Time spent investigating and patching the same symptoms repeatedly

---

## Resolution

### PR #146: Comprehensive Fix

**Changes:**

| File | Change | Addresses |
|------|--------|-----------|
| `config/settings/base.py` | Fix `_sentry_before_send` logger check order; add PEEBOT-F filter; allow `localhost`/`127.0.0.1` in `ALLOWED_HOSTS` | PEEBOT-D, PEEBOT-F, healthchecks |
| `config/tests/test_sentry_filter.py` | Add `TestEventProcessorsOperationalErrorFilter` and `TestCeleryConsumerLogFilter` | Test coverage |
| `docker/prod/docker-compose.yml` | Add `stop_grace_period: 60s` to `worker`, `beat`, `ingestion`; add `stop_grace_period: 30s` to `web` | Graceful shutdown |

**Server cleanup:**
- Stopped and removed 14 stale containers from `pr-104` and `pr-105` deployments

### Verification

- `just test`: 194/194 tests pass
- `ruff check` / `ruff format` / `mypy`: all passed
- Post-deploy monitoring: **zero new Sentry events** after PR #146 deployment

---

## What Went Well

1. **Existing retry logic was correct**: Celery tasks already had `autoretry_for=(OperationalError,)`, `close_old_connections()`, and graceful degradation. The code didn't need fixing — the monitoring did.
2. **Multi-agent investigation**: Using parallel subagents to investigate code, infrastructure, and Sentry event structures simultaneously uncovered the real root cause faster than sequential debugging.
3. **Test coverage**: The Sentry filter had comprehensive tests, which made it safe to extend without regression fears.
4. **Incremental fixes were partially effective**: PRs #143, #144, #145 each addressed real gaps, even if they didn't solve the whole problem.

---

## What Went Wrong

1. **Assumed rolling restarts**: Documentation stated Coolify does "rolling restarts," but the actual Docker Compose behavior was container recreation. This assumption delayed infrastructure-focused investigation.
2. **Band-aid fixes without root cause**: The first 3 PRs (#143, #144, #145) treated symptoms individually without asking "why do these only happen on deploy?"
3. **Stale environments left running**: PR preview containers were never cleaned up, causing healthcheck failures and potential DNS confusion for 5+ weeks.
4. **PEEBOT-D structural bug survived review**: PR #144's description claimed to move the logger check before the exception check, but the merged code didn't actually do this. Review missed the discrepancy.
5. **Sentry is the only health monitor**: With no Grafana/Coolify healthcheck dashboard, we had no way to distinguish deploy noise from real outages without reading Sentry events.

---

## Action Items

| # | Action | Owner | Priority | Status |
|---|--------|-------|----------|--------|
| 1 | Configure Coolify to auto-delete PR preview deployments after merge | Onur | High | Pending |
| 2 | Add Grafana or Coolify-native healthcheck dashboard (independent of Sentry) | Onur | Medium | Pending |
| 3 | Document Docker Compose deploy behavior in `docs/system-solution/` | Onur | Low | Pending |
| 4 | Investigate PEEBOT-W/X (OpenRouter 429 rate limits) — separate concern | Onur | Low | Open (#126) |
| 5 | Investigate PEEBOT-2 (`SoftTimeLimitExceeded`) — potential real issue | Onur | Low | Open |
| 6 | Verify `stop_grace_period` effectiveness on next deploy — confirm no mid-flight SIGKILLs | Onur | Medium | Pending |

---

## Lessons Learned

1. **Correlation with deploys is a signal, not noise**: If errors cluster within minutes of every deployment, the deploy process itself is the bug — not the code.
2. **Filter structural bugs are subtle**: Moving a line of code before or after an early return can completely change behavior. Code review should explicitly verify the execution path.
3. **Docker Compose defaults are dangerous**: The 10s `stop_grace_period` default is almost always too short for stateful services. Explicitly set it.
4. **Stale environments compound problems**: Old preview deployments aren't just resource waste — they can break healthchecks and confuse DNS resolution.
5. **Multiple monitoring layers**: Relying on Sentry as the sole health monitor means every transient hiccup becomes an alert. A separate healthcheck dashboard would have shown "all green" during deploys, immediately flagging the issue as noise.

---

## Appendix: Sentry Event Structures

Understanding the event types was critical to fixing the filters:

### PEEBOT-D (Log Message Event)
```python
{
    "type": "default",  # No exception field!
    "logger": "celery.worker.consumer.consumer",
    "logentry": {
        "message": "consumer: Cannot connect to %s: %s.\n%s\n",
        "formatted": "consumer: Cannot connect to redis://redis:6379/0: ...",
    },
}
```

### PEEBOT-F (Exception Event)
```python
{
    "exception": {
        "values": [{
            "type": "OperationalError",
            "module": "psycopg",
        }]
    },
    "culprit": "apps.event_processors.tasks.run_peebot_processor",
    "logger": None,  # Captured by CeleryIntegration, not LoggingIntegration
}
```

### PEEBOT-E (LoggingIntegration Exception Event)
```python
{
    "exception": {
        "values": [{
            "type": "OperationalError",
            "module": "django.db.utils",
        }]
    },
    "logger": "apps.telemetry_ingestion.management.commands.run_lightstreamer",
    "level": "warning",  # WARNING log with exc_info=True
}
```

---

## Related PRs and Issues

- **PR #146**: `🐛 fix: suppress deploy-restart noise in Sentry and improve graceful shutdown` (final fix)
- **PR #145**: `🐛 fix: filter ingestion flush_buffer OperationalError in Sentry (PEEBOT-E)`
- **PR #144**: `🐛 fix: filter Celery consumer log messages in Sentry before_send (PEEBOT-D)`
- **PR #143**: `🐛 fix: suppress transient deploy-restart noise in Sentry`
- **Issue #139**: PEEBOT-F
- **Issue #140**: PEEBOT-C
- **Issue #142**: PEEBOT-10/11
- **Issue #127**: PEEBOT-E
- **Issue #125**: PEEBOT-D

---

*Document generated: 2026-04-25*
