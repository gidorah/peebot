# Product Guidelines

## Architectural Standards
1.  **Single Source of Truth:** All telemetry data must reside in the central TimescaleDB hypertable (`TelemetryReading`). This ensures consistency and simplifies analytics queries.

## Content & Persona Guidelines
1.  **Concise & Witty:** Tweets should be short, punchy, and prioritize humor over technical jargon. The goal is to entertain first, inform second.
2.  **Visual Language:** Use space-themed emojis (🚀, 🛰️, 🌌, 🚽) sparingly but effectively to enhance the personality of the posts without cluttering them.

## Reliability & Data Integrity
1.  **Data Completeness:** The system must be robust enough to handle gaps or interruptions in the Lightstreamer feed without crashing or entering an inconsistent state.
2.  **Idempotency:** The analytics engine must be idempotent. Processing the same telemetry packet or time window multiple times must not result in duplicate events or duplicate tweets.

## Development Workflow & Standards
1.  **Test-Driven Development (TDD):** Developers should write failing tests for new event detectors or logic before implementing the code.
2.  **Strict Typing:** All new code must adhere to strict type checking standards (`mypy --strict`) to ensure code quality and reduce runtime errors.
3.  **Commit Protocol:** All commits must be made using the global `/commit` command provided by the OpenCode environment to ensure safety checks and conventional formatting are applied automatically.

## Documentation
1.  **Self-Documenting Code:** Prioritize clear, descriptive variable names and comprehensive type hints over excessive inline comments.
2.  **Architecture Decision Records (ADRs):** Significant architectural choices must be documented in `docs/adr/` to preserve the context of decisions.
3.  **Live API Docs:** Keep OpenAPI/Swagger documentation up-to-date for all internal APIs to facilitate easier integration and debugging.
