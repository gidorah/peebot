# Copilot Agent Instructions

## Terminal Execution – Known Issue Workaround

VS Code's terminal tool has an internal idle timeout that fires when a command produces no output for ~500ms. This causes premature returns for commands like `just test` and `uv run mypy .` where there's a silent gap (DB setup, module scanning).

**CRITICAL: For `just test`, `just test-fresh`, `uv run mypy`, and any test/lint/build commands:**
1. Run the command with `isBackground: true` to launch it without waiting
2. Use `await_terminal` with a generous timeout (e.g., 120000ms) to wait for completion and get the output
3. NEVER run these commands with `isBackground: false` — the terminal tool will return prematurely and you'll get incomplete output

Example pattern:
```
Step 1: run_in_terminal(command="just test", isBackground=true)  → returns terminal ID
Step 2: await_terminal(id=<terminal_id>, timeout=120000)         → returns full output
```

## Project Context

- This is a Django modular monolith using TimescaleDB.
- Package manager: `uv` (always use `uv run`, `uv sync`).
- Task runner: `just` (see Justfile for available commands).
- Tests: ALWAYS use `just test` — never run `pytest` directly.
- Linter: `ruff`. Type checker: `mypy` via `uv run mypy apps/`.
