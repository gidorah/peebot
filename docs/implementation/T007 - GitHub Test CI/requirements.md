# Requirements: T007 - GitHub Test CI

## 1. Objective

Introduce GitHub Actions-based test CI so every pull request creation and every new commit pushed to an open pull request automatically runs the PeeBot test suite before merge.

## 2. Scope

This task covers:

- A GitHub Actions workflow for pull request test execution.
- Minimal supporting repository changes required to run the canonical test command in CI.
- Documentation updates describing the workflow and its local reproduction path.

This task does not cover:

- Deployment workflows.
- Release automation.
- Full lint/type-check CI expansion beyond test execution.

## 3. Functional Requirements

- FR-CI-001: A workflow shall run when a pull request targeting `main` is opened.
- FR-CI-002: A workflow shall run when new commits are pushed to an existing pull request.
- FR-CI-003: A workflow shall run when a closed and re-opened pull request becomes active again.
- FR-CI-004: The workflow shall execute the project's canonical test entrypoint via `just test` rather than invoking `pytest` directly.
- FR-CI-005: The workflow shall provision a database compatible with PeeBot's TimescaleDB migrations.
- FR-CI-006: The workflow shall not require production or third-party API secrets to execute safely on pull requests.
- FR-CI-007: The workflow shall cancel outdated in-progress runs for the same pull request when a newer commit is pushed.
- FR-CI-008: The workflow shall support manual execution via `workflow_dispatch` for maintainers.

## 4. Non-Functional Requirements

- NFR-CI-001: The workflow shall use pinned major versions for third-party GitHub Actions.
- NFR-CI-002: The workflow shall use dependency caching appropriate for the `uv`-managed Python environment.
- NFR-CI-003: The workflow shall use least-privilege job permissions.
- NFR-CI-004: The workflow shall keep configuration simple enough to be reproduced locally by contributors.

## 5. Constraints

- C-CI-001: The repository standard says tests must run through `just test`, not raw `pytest`.
- C-CI-002: `config/settings/testing.py` expects direct database access for pytest database creation, so CI must bypass PgBouncer and connect directly to the database service.
- C-CI-003: `apps/telemetry_storage` migrations use TimescaleDB features, so plain PostgreSQL service images are not sufficient.
- C-CI-004: Pull request workflows must remain safe for forked PRs; avoid `pull_request_target` and avoid secrets.

## 6. Architectural Exception

The project architecture requires pooled database access for normal application traffic. This CI task does not change that production rule. The direct `TEST_DATABASE_URL` path is a test-only exception required by pytest-django so the workflow can create and destroy ephemeral test databases without PgBouncer involvement.

## 7. Success Criteria

- A PR opened against `main` triggers the workflow automatically.
- A commit pushed to that PR triggers the workflow again automatically.
- The workflow uses a TimescaleDB service container and completes with `just test`.
- Contributors can reproduce the CI test path locally from documented commands.
