# Requirements: T008 - Quality CI

## 1. Objective

Extend GitHub pull request CI so PeeBot also runs static quality gates for Ruff and mypy on every pull request update, alongside the existing test workflow.

## 2. Scope

This task covers:

- GitHub Actions checks for Ruff linting.
- GitHub Actions checks for mypy type checking.
- Minimal documentation updates for the new CI checks and local reproduction commands.

This task does not cover:

- Formatting automation or auto-fix commits.
- Dependency security scanning changes.
- Test workflow redesign.

## 3. Functional Requirements

- FR-QCI-001: Pull request CI shall run Ruff on PR open, synchronize, and reopen events targeting `main`.
- FR-QCI-002: Pull request CI shall run mypy on PR open, synchronize, and reopen events targeting `main`.
- FR-QCI-003: The quality checks shall support `workflow_dispatch` for maintainers.
- FR-QCI-004: The workflow shall report separate check names for linting and type checking so branch protection can target them individually.
- FR-QCI-005: The workflow shall install project dependencies using the existing `uv`-managed environment.

## 4. Non-Functional Requirements

- NFR-QCI-000: The workflow shall use pinned major versions for third-party GitHub Actions.
- NFR-QCI-001: The workflow shall use least-privilege permissions.
- NFR-QCI-002: The workflow shall use dependency caching appropriate for `uv`.
- NFR-QCI-003: The workflow shall avoid unnecessary service containers because Ruff and mypy do not require TimescaleDB or Redis.
- NFR-QCI-004: Contributors shall be able to reproduce the CI checks locally from documented commands.

## 5. Constraints

- C-QCI-001: The repo standard says lint issues must be fixed at the root cause, not bypassed.
- C-QCI-002: Mypy should follow the repository's current local command scope, `uv run mypy apps/`, unless implementation reveals a stronger project-native target.
- C-QCI-003: The new quality workflow must remain safe for forked PRs and shall not use secrets.

## 6. Success Criteria

- A PR opened against `main` triggers Ruff and mypy checks automatically.
- A commit pushed to that PR reruns Ruff and mypy automatically.
- The quality workflow runs without database service containers.
- README and roadmap documentation describe the new checks and local reproduction path.
