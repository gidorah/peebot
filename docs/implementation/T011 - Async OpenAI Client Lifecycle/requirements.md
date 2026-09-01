# T011: Async OpenAI Client Lifecycle — Requirements

## Context

Sentry issue `PEEBOT-15` reports recurring `RuntimeError: Event loop is closed`
events from `httpx.AsyncClient.aclose()` after the PeeBot Celery task completes.
Each task uses a fresh `asyncio.run()` event loop, while `JokeGenerator` creates an
`AsyncOpenAI` client without explicitly closing it.

## Requirements

1. `JokeGenerator` must explicitly own and close its `AsyncOpenAI` client on the
   event loop that used it.
2. Cleanup must run after successful generation, an empty result, an exception,
   an early return, or coroutine cancellation.
3. A known Bluesky cooldown must be checked before allocating `JokeGenerator`.
4. Existing event detection, joke generation, and Bluesky posting behavior must
   remain unchanged.
5. The Celery task must continue using its existing `asyncio.run()` boundary.
6. Sentry filtering must not be used to hide the error.

## Acceptance Criteria

- A real OpenAI/httpx transport can be used and released across two separate
  `asyncio.run()` loops without an un-retrieved `Event loop is closed` exception.
- The OpenAI client is closed on normal, empty-result, exception, and cancellation
  paths.
- An active initial cooldown does not construct `JokeGenerator`.
- The complete test suite, lint checks, and focused type checks pass.
