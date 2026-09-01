# T011: Async OpenAI Client Lifecycle — Tasks

- [x] Reproduce the Sentry signature with a real OpenAI/httpx keep-alive transport.
- [x] Add an async lifecycle contract to `JokeGenerator`.
- [x] Await OpenAI client closure whenever the generator context exits.
- [x] Move generator allocation below the initial Bluesky cooldown check.
- [x] Update task and integration mocks for async context management.
- [x] Test successful, empty-result, raised-error, and cancellation cleanup paths.
- [x] Add the cross-loop real-transport regression test.
- [x] Run the complete test suite, lint checks, and focused type checks.
