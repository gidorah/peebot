# Design: T007 - GitHub Test CI

## 1. Overview

This task adds a single GitHub Actions workflow dedicated to pull request test execution. The design intentionally mirrors the repository's existing testing contract: contributors and CI both use `just test`, while the workflow supplies an ephemeral CI-specific environment and a TimescaleDB service container.

The implementation stays narrow. It does not introduce a full quality pipeline or deployment automation. The goal is to establish a reliable PR gate that validates Django, pytest, and TimescaleDB-backed behavior on every relevant PR update.

## 2. Workflow Architecture

### 2.1 Trigger Model

The workflow listens to the `pull_request` event for `main` with these activity types:

- `opened`
- `synchronize`
- `reopened`

This combination covers:

- initial PR creation,
- every new commit pushed to the PR branch,
- PRs that are reopened after being closed.

A `workflow_dispatch` trigger is also included for manual reruns.

### 2.2 Concurrency Model

The workflow defines a PR-scoped concurrency group and enables `cancel-in-progress`. When a contributor pushes multiple commits in quick succession, GitHub cancels stale runs and keeps only the newest one active. This reduces queue waste and shortens feedback loops.

## 3. Execution Environment

### 3.1 Runner and Dependencies

The workflow uses `ubuntu-latest` and installs project tooling via:

- `actions/checkout`
- `astral-sh/setup-uv`
- a lightweight `just` installation step

`setup-uv` cache support is enabled so the `uv.lock`-backed environment can be restored efficiently between runs.

### 3.2 Database Service

The workflow uses a TimescaleDB service container rather than vanilla PostgreSQL because PeeBot migrations call Timescale-specific functions such as `create_hypertable`. Using Timescale in CI prevents schema drift between CI and real environments.

The job sets both `DATABASE_URL` and `TEST_DATABASE_URL` to the service container's direct port `5432`. This matches `config/settings/testing.py`, which bypasses PgBouncer so pytest-django can create and destroy the temporary test database.

This is explicitly a CI and test-environment exception. It does not alter the production architecture rule that normal application traffic should use pooled database connections.

## 4. Test Command Strategy

The repository standard requires `just test`, but the current `Justfile` hardcodes `DOTENV_PATH=.env.local`. That makes CI difficult because GitHub Actions should not depend on a developer-local env file.

The chosen design is to parameterize the recipe:

```just
DOTENV_PATH="${DOTENV_PATH:-.env.local}" uv run pytest {{args}}
```

This preserves local behavior while allowing CI to inject a CI-specific env file path. The workflow will generate a minimal `.env.ci` file at runtime containing only non-secret values needed by Django settings and the test database connection.

## 5. Security and Safety

- Use `pull_request`, not `pull_request_target`, because the workflow executes untrusted contributor code.
- Do not inject OpenRouter, Bluesky, or production secrets.
- Set `permissions: contents: read`.
- Keep CI env values synthetic and non-sensitive.

## 6. Documentation Changes

The task updates the roadmap and README so the repository documents:

- that PR test CI exists,
- which events trigger it,
- how to reproduce the CI command locally.

## 7. Alternatives Considered

### 7.1 Rejected: Docker Compose-based CI

Running `just dev-test` inside GitHub Actions would more closely resemble the local container stack, but it adds startup overhead, more moving parts, and unnecessary services for the current goal.

### 7.2 Rejected: Plain PostgreSQL Service

This is simpler to declare, but it fails the project's TimescaleDB migration requirements and would create a false-positive CI environment.

### 7.3 Rejected: Direct `pytest` in Workflow

This conflicts with the repository's documented testing contract. Keeping `just test` as the single test entrypoint reduces drift between local and CI execution.
