# Project Workflow

This document outlines the standard workflow for all tasks within this project.

## 1. Commit Protocol

- **Frequency:** Commit changes after **each phase** is verified and complete.
- **Message Format:** Use the Conventional Commits specification (e.g., `feat:`, `fix:`, `chore:`).
- **Task Summary:** Append the detailed task summary to the **commit message body**.

## 2. Testing Standards

- **Test-Driven Development (TDD):** TDD is strictly required. Tests must be written and fail *before* any implementation code is written.
- **Coverage Requirement:** Code coverage must be maintained above **80%**.
- **Test Scope:** All new features and bug fixes must have accompanying unit and/or integration tests.

## 3. Phase Completion Protocol

At the end of each phase, you must perform the following:

1.  **Verify Requirements:** Ensure all tasks in the phase are marked as completed.
2.  **Run Full Test Suite:** Execute the full test suite to ensure no regressions.
3.  **Check Coverage:** Verify that the code coverage meets the 80% threshold.
4.  **Lint & Format:** Run linter and formatter (ruff) to ensure code style compliance.
5.  **Commit:** Create a single commit for the entire phase with a summary of changes.

## 4. Documentation

- **Update Docs:** Update `product.md`, `tech-stack.md`, or `product-guidelines.md` if the phase introduced any architectural or product-level changes.
- **Update ADRs:** Create a new Architecture Decision Record if a significant design decision was made.
