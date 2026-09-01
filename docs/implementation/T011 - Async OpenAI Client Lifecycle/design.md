# T011: Async OpenAI Client Lifecycle — Design

## Root Cause

`JokeGenerator` creates an `AsyncOpenAI` client whose underlying httpx transport
is bound to the current Celery task's event loop. Without explicit closure, the
OpenAI SDK destructor may schedule `AsyncClient.aclose()` during garbage
collection on a later task's loop. The transport then tries to use its original,
already-closed loop and raises `RuntimeError: Event loop is closed`.

## Design

`JokeGenerator` implements the asynchronous context-manager protocol:

- `__aenter__` returns the configured generator.
- `__aexit__` awaits `AsyncOpenAI.close()`.

The task checks the Bluesky cooldown before constructing the generator. When
posting is allowed, joke generation runs inside `async with JokeGenerator()`.
Leaving that block closes the HTTP transport before control can return to the
`asyncio.run()` boundary. Bluesky posting happens after the OpenAI client closes.

This keeps resource ownership with the object that acquires the client, covers
all control-flow exits through Python's context-manager semantics, and avoids
changing the established Celery/event-loop boundary.

## Verification

A regression test uses the locked OpenAI SDK against a local HTTP/1.1 keep-alive
server. It uses the client on one `asyncio.run()` loop, releases it on a second
loop, and asserts that the loop exception handler receives no cleanup error.
Tests cover cooldown, successful generation, empty output, raised errors, and
cancellation cleanup across the task-orchestration and service-lifecycle seams.
