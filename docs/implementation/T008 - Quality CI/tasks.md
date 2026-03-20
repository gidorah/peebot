# Tasks: T008 - Quality CI

## Phase 1: Spec and roadmap alignment

- [x] Add implementation docs for requirements, design, and tasks.
- [x] Update `docs/system-solution/main-tasks.md` with the T008 roadmap entry before code changes.
- [x] Review the new implementation docs against repository workflow and existing T007 CI conventions.

## Phase 2: CI implementation

- [x] Create a GitHub Actions workflow for PR quality checks.
- [x] Add a `ruff` job using `uv run ruff check .`.
- [x] Add a `mypy` job using `uv run mypy apps/`.
- [x] Add `workflow_dispatch`, concurrency cancellation, and least-privilege permissions.

## Phase 3: Documentation and verification

- [x] Update `README.md` with the new PR quality checks and local reproduction commands.
- [x] Validate workflow YAML and run the local Ruff and mypy commands.

Completed in PR #100.
