# Design: T008 - Quality CI

## 1. Overview

This task adds a dedicated GitHub Actions workflow, `pr-quality.yml`, for static quality checks. The design keeps it separate from `PR Tests` because Ruff and mypy do not need TimescaleDB, Redis, or Django test database setup. Splitting the concerns keeps the quality checks faster, easier to debug, and independently enforceable in branch protection.

## 2. Workflow Architecture

### 2.1 Trigger Model

The workflow listens to:

- `pull_request` on `main`
- types: `opened`, `synchronize`, `reopened`
- `workflow_dispatch`

This matches the trigger behavior already used for `PR Tests`, so every new PR commit reruns both the test and quality gates.

### 2.2 Job Model

The workflow defines two independent jobs:

- `ruff`
- `mypy`

They run in parallel on `ubuntu-latest` and share the same basic setup:

- `actions/checkout@v5`
- `astral-sh/setup-uv@v7`
- `uv sync --frozen --dev`

The `setup-uv` configuration mirrors the existing T007 workflow conventions with:

- `python-version`: matching the value configured in `.github/workflows/pr-quality.yml`
- `enable-cache: true`

No service containers are needed.

## 3. Command Strategy

The implementation uses the repository's existing local commands directly rather than inventing CI-only command variants:

- Ruff: `uv run ruff check .`
- mypy: `uv run mypy apps/`

This aligns CI with the commands already documented in `README.md`. It intentionally uses direct `uv run` commands rather than adding new `just` recipes because the current repository already documents quality checks that way.

## 4. Concurrency and Permissions

The workflow uses PR-scoped concurrency with `cancel-in-progress: true`, mirroring the existing test workflow. This prevents duplicate lint/type runs when several commits are pushed in a short time.

Permissions stay at `contents: read`.

## 5. Alternatives Considered

### 5.1 Rejected: Add Ruff and mypy to the test workflow job

This would reduce the number of workflow files, but it would also serialize unrelated checks behind the slower test job and make failures less clear.

### 5.2 Rejected: Reuse `just dev-check`

`just dev-check` is Docker-oriented and runs inside the web container. For GitHub Actions, direct runner execution with `uv sync --frozen --dev` is simpler and avoids unnecessary container overhead.

## 6. Documentation Changes

The task updates the roadmap and README so contributors can see:

- which PR quality checks now run automatically,
- which commands reproduce those checks locally.
