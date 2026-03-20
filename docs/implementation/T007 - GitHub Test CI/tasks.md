# Tasks: T007 - GitHub Test CI

## Phase 1: Spec and repo alignment

- [ ] Confirm next available implementation task ID and avoid numbering collisions.
- [ ] Update `docs/system-solution/main-tasks.md` so the roadmap reflects post-T005 work and registers T007 before code changes.
- [ ] Add implementation docs for requirements, design, and tasks.
- [ ] Review the new implementation docs against `docs/system-solution` guidance.

## Phase 2: CI implementation

- [ ] Update `Justfile` so `just test` can use a CI-provided `DOTENV_PATH` while preserving `.env.local` as the local default.
- [ ] Create `.github/workflows/pr-tests.yml` for pull request test execution.
- [ ] Provision a TimescaleDB service container in the workflow.
- [ ] Configure a minimal CI env file and execute `just test`.
- [ ] Add concurrency cancellation and least-privilege permissions.

## Phase 3: Documentation and verification

- [ ] Update `README.md` with the PR CI behavior and local reproduction notes.
- [ ] Validate workflow YAML syntax and run a targeted local verification for `DOTENV_PATH=.env.ci just test`.
