# Tasks: T008 - Quality CI

## Phase 1: Spec and roadmap alignment

- [ ] Add implementation docs for requirements, design, and tasks.
- [ ] Update `docs/system-solution/main-tasks.md` with the T008 roadmap entry before code changes.
- [ ] Review the new implementation docs against repository workflow and existing T007 CI conventions.

## Phase 2: CI implementation

- [ ] Create a GitHub Actions workflow for PR quality checks.
- [ ] Add a `ruff` job using `uv run ruff check .`.
- [ ] Add a `mypy` job using `uv run mypy apps/`.
- [ ] Add `workflow_dispatch`, concurrency cancellation, and least-privilege permissions.

## Phase 3: Documentation and verification

- [ ] Update `README.md` with the new PR quality checks and local reproduction commands.
- [ ] Validate workflow YAML and run the local Ruff and mypy commands.
