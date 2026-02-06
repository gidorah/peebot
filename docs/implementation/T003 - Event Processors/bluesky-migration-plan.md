# Bluesky Integration Plan

## Overview

Replace Twitter integration with Bluesky for social media posting. Bluesky offers a **free, open API** with no rate limits for posting, making it ideal for PeeBot's use case.

## Why Bluesky?

| Aspect | Twitter/X | Bluesky |
|--------|-----------|---------|
| **Pricing** | $200/mo (Basic) or Pay-Per-Use | **Free** |
| **Post API** | Requires credits/subscription | Free, no limits |
| **Rate Limits** | Strict | Generous (5 posts/second) |
| **SDK** | tweepy (OAuth complexity) | `atproto` (simple auth) |
| **API Stability** | Frequent changes | Stable AT Protocol |

## Technical Approach

### SDK: `atproto`

- **Package**: `atproto` (PyPI)
- **Documentation**: https://atproto.blue
- **GitHub**: https://github.com/MarshalX/atproto
- **Auth**: App Password (no OAuth dance needed)

### Basic Usage

```python
from atproto import Client

client = Client()
client.login('handle.bsky.social', 'app-password')
post = client.send_post('Hello from PeeBot! 🚽🛰️')
# Returns: post.uri, post.cid
```

## Implementation Tasks

### Phase 1: Add Bluesky Client Service

- [x] **Task 1.1**: Add `atproto` dependency
  - File: `pyproject.toml`
  - Command: `uv add atproto`

- [x] **Task 1.2**: Create `BlueskyClient` service
  - File: `apps/event_processors/services/bluesky_client.py`
  - Mirror `TwitterClient` interface:
    - `__init__()` - Initialize with credentials
    - `check_cooldown()` - Query SocialPost for recent posts
    - `post(text, event)` - Post to Bluesky, create SocialPost record
    - `_create_failed_post()` - Record failures

- [x] **Task 1.3**: Add environment configuration
  - File: `config/settings/base.py`, `.env.example`
  - Settings:
    - `BLUESKY_HANDLE` (e.g., `peebot.bsky.social`)
    - `BLUESKY_APP_PASSWORD` (from Bluesky settings)

### Phase 2: Update Task Orchestration

- [x] **Task 2.1**: Update Celery task to use BlueskyClient
  - File: `apps/event_processors/tasks.py`
  - Replace TwitterClient instantiation with BlueskyClient
  - Keep fallback logic for graceful degradation

- [x] **Task 2.2**: Update SocialPost platform field
  - Add `"bluesky"` as platform value
  - BlueskyClient should use `platform="bluesky"`

### Phase 3: Testing

- [x] **Task 3.1**: Create unit tests for BlueskyClient
  - File: `apps/event_processors/tests/test_bluesky_client.py`
  - Mock `atproto.Client`
  - Test: successful post, cooldown, error handling

- [x] **Task 3.2**: Update integration tests
  - File: `tests/test_event_processors_integration.py`
  - Mock BlueskyClient instead of TwitterClient

- [x] **Task 3.3**: Manual E2E verification
  - Create Bluesky account for PeeBot
  - Generate App Password
  - Test posting with real credentials

### Phase 4: Cleanup (Optional)

- [x] **Task 4.1**: Remove Twitter dependencies (optional)
  - Keep if you want multi-platform support
  - Remove `tweepy` if Twitter-only

- [x] **Task 4.2**: Update documentation
  - README.md
  - Module docstrings

## BlueskyClient Interface Design

```python
class BlueskyClient:
    """Client for posting to Bluesky about detected events."""

    PLATFORM = "bluesky"
    DEFAULT_COOLDOWN_MINUTES = 30

    def __init__(self) -> None:
        """Initialize with credentials from settings."""
        handle = settings.BLUESKY_HANDLE
        app_password = settings.BLUESKY_APP_PASSWORD

        self.client = Client()
        self.client.login(handle, app_password)

    async def check_cooldown(self) -> tuple[bool, timedelta | None]:
        """Check if cooldown has elapsed since last successful post."""
        # Query SocialPost with platform="bluesky", status="success"
        ...

    async def post(self, text: str, event: DetectedEvent) -> str | None:
        """Post to Bluesky and create SocialPost record.

        Returns:
            Post URI if successful, None otherwise
        """
        # 1. Check cooldown
        # 2. Post via self.client.send_post(text)
        # 3. Create SocialPost with status=SUCCESS
        # 4. On error, create SocialPost with status=FAILED
        ...

    async def _create_failed_post(
        self, event: DetectedEvent, text: str, error_message: str
    ) -> SocialPost:
        """Create SocialPost record with failed status."""
        ...
```

## Configuration Example

```bash
# .env
BLUESKY_HANDLE=peebot.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

## Getting Bluesky Credentials

1. Create account at https://bsky.app
2. Go to Settings → App Passwords
3. Create new App Password (name: "PeeBot API")
4. Copy the password (shown only once)

## Estimated Effort

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Phase 1 | Add BlueskyClient | 1-2 hours |
| Phase 2 | Update tasks.py | 30 min |
| Phase 3 | Testing | 1-2 hours |
| Phase 4 | Cleanup | 30 min |
| **Total** | | **3-5 hours** |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Bluesky API changes | AT Protocol is stable, SDK handles versioning |
| Account suspension | Follow Bluesky ToS, avoid spam |
| Rate limiting | 5 posts/sec limit is very generous |

## Multi-Platform Support (Future)

The current design with `SocialPost.platform` field allows supporting multiple platforms simultaneously. You could:

1. Keep both `TwitterClient` and `BlueskyClient`
2. Post to both platforms when event detected
3. Independent cooldowns per platform

For now, we'll replace Twitter with Bluesky only.
