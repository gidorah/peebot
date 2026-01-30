# Implementation Plan: T003 - Event Processors

## Phase 1: Module Setup

- [ ] **Step 1**: Create Django app structure.
    - *Command*: `uv run python manage.py startapp event_processors apps/event_processors`
    - *Task*: Create subdirectories `processors/`, `services/`, `tests/`.
    - *Verification*: Directory structure matches design.md section 2.

- [ ] **Step 2**: Register app in Django settings.
    - *File*: `config/settings/base.py`
    - *Task*: Add `apps.event_processors` to `INSTALLED_APPS`.
    - *Verification*: `uv run python manage.py check` passes.

## Phase 2: Data Models

- [ ] **Step 3**: Implement `ProcessorState` model.
    - *File*: `apps/event_processors/models.py`
    - *Task*: Define model with fields per design.md section 3.2. Inherit from `UUID7Model` and `TimeStampedModel`. Add unique constraint on `processor_name`.
    - *Test*: `apps/event_processors/tests/test_models.py` — verify CRUD operations, state persistence, unique constraint enforcement.

- [ ] **Step 4**: Implement `DetectedEvent` model.
    - *File*: `apps/event_processors/models.py`
    - *Task*: Define model with fields per design.md section 3.1. Inherit from `UUID7Model` and `TimeStampedModel`. Add index on `(event_type, -detected_at)`.
    - *Test*: Extend `test_models.py` — verify field types, index exists.

- [ ] **Step 4b**: Implement `SocialPost` model.
    - *File*: `apps/event_processors/models.py`
    - *Task*: Define model with fields per design.md section 3.3. Inherit from `UUID7Model` and `TimeStampedModel`. Add FK to `DetectedEvent`. Add index on `(platform, -posted_at)`.
    - *Test*: Extend `test_models.py` — verify FK relationship, cooldown query works.

- [ ] **Step 5**: Create and apply migrations.
    - *Command*: `uv run python manage.py makemigrations event_processors`
    - *Command*: `uv run python manage.py migrate`
    - *Verification*: Tables exist in database.

## Phase 3: Base Processor Infrastructure

- [ ] **Step 6**: Implement `BaseProcessor` abstract class.
    - *File*: `apps/event_processors/processors/base.py`
    - *Task*: Define abstract class with attributes (`processor_name`, `channel_pui`, `poll_interval_seconds`, `window_minutes`) and abstract methods (`analyze`, `get_confidence`). Include state load/save helpers.
    - *Test*: `apps/event_processors/tests/test_base_processor.py` — verify abstract enforcement, state helper methods.

- [ ] **Step 7**: Implement jitter utility.
    - *File*: `apps/event_processors/processors/base.py`
    - *Task*: Add async method for random 0–5 second delay before execution.
    - *Test*: Verify delay is within expected range (mock `asyncio.sleep`).

## Phase 4: PeeBot Processor

- [ ] **Step 8**: Implement `PeeBotProcessor` class.
    - *File*: `apps/event_processors/processors/pee_bot.py`
    - *Task*: Inherit from `BaseProcessor`. Set channel to `NODE3000004`. Implement `analyze()` with burst detection and glitch filtering logic per design.md section 4.4.
    - *Test*: `apps/event_processors/tests/test_pee_bot.py` — test with mock readings:
        - Sustained burst (30s-2min) with stable post-burst → event detected
        - Spike that immediately reverts → glitch rejected, no event
        - Flat/decreasing readings → no event
        - Burst too short (< 30s) → no event
        - Insufficient data → no event

- [ ] **Step 9**: Implement confidence calculation.
    - *File*: `apps/event_processors/processors/pee_bot.py`
    - *Task*: Implement `get_confidence()` based on trend strength/consistency.
    - *Test*: Verify confidence values are within 0.0–1.0 range.

## Phase 5: External Services

- [ ] **Step 10**: Implement `JokeGenerator` service.
    - *File*: `apps/event_processors/services/joke_generator.py`
    - *Task*: Create class using `openai` SDK. Configure for OpenRouter endpoint and DeepSeek model. Implement `generate(event)` method with prompt for "dry, scientific, slightly absurd" tone.
    - *Test*: `apps/event_processors/tests/test_joke_generator.py` — mock OpenAI client, verify prompt includes event context, verify retry logic on failure.

- [ ] **Step 11**: Implement `TwitterClient` service.
    - *File*: `apps/event_processors/services/twitter_client.py`
    - *Task*: Create class using `tweepy`. Implement `post(text, event)` method that posts to Twitter and creates `SocialPost` record. Implement `check_cooldown()` querying `SocialPost` for posts within last 30 minutes.
    - *Test*: `apps/event_processors/tests/test_twitter_client.py` — mock tweepy, verify cooldown logic blocks/allows correctly, verify `SocialPost` created on success.

- [ ] **Step 12**: Add environment configuration for API keys.
    - *File*: `config/settings/base.py`, `.env.example`
    - *Task*: Add settings for `OPENROUTER_API_KEY`, `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`.
    - *Verification*: Settings load without error when env vars present.

## Phase 6: Celery Integration

- [ ] **Step 13**: Implement Celery task for PeeBot.
    - *File*: `apps/event_processors/tasks.py`
    - *Task*: Create `run_peebot_processor` task. Task should: apply jitter, load processor state, query readings, run analysis, create `DetectedEvent` if detected, check cooldown, generate joke, post to Twitter, update processor state.
    - *Test*: `apps/event_processors/tests/test_tasks.py` — use `pytest-celery` eager mode, mock external services, verify full flow.

- [ ] **Step 14**: Register task in Celery Beat schedule.
    - *File*: `config/celery.py`
    - *Task*: Add `peebot-processor` to `beat_schedule` with 30-second interval.
    - *Verification*: `uv run celery -A config inspect scheduled` shows task.

## Phase 7: Error Handling & Logging

- [ ] **Step 15**: Add structured logging throughout module.
    - *Files*: All module files
    - *Task*: Use `structlog` for all log statements. Include `processor_name`, `event_type`, `channel_id` in log context.
    - *Verification*: Logs appear in Seq during manual testing.

- [ ] **Step 16**: Implement error handling per design.md section 7.
    - *Files*: `tasks.py`, service files
    - *Task*: Add try/except blocks with appropriate strategies (retry, skip, log). Ensure `last_run_at` updates even on failure.
    - *Test*: Simulate failures (mock exceptions), verify graceful handling.

## Phase 8: Integration Testing

- [ ] **Step 17**: Create integration test for full processor flow.
    - *File*: `tests/test_event_processors_integration.py`
    - *Task*: Use `model_bakery` to create realistic `TelemetryReading` data. Run processor task. Verify `DetectedEvent` created with correct fields.
    - *Verification*: `uv run pytest tests/test_event_processors_integration.py`

- [ ] **Step 18**: Manual end-to-end verification.
    - *Task*: Start Celery worker and beat. Inject test telemetry data with increasing trend. Observe event detection and (with mocked Twitter) posting flow.
    - *Commands*:
        - `uv run celery -A config worker -l info`
        - `uv run celery -A config beat -l info`
    - *Verification*: `DetectedEvent` record created in database.

## Phase 9: Documentation

- [ ] **Step 19**: Update module docstrings.
    - *Files*: All `.py` files in module
    - *Task*: Add module-level docstrings explaining purpose. Add class/method docstrings for public interfaces.

- [ ] **Step 20**: Update project README.
    - *File*: `README.md`
    - *Task*: Add section describing Event Processors module, how to configure API keys, and how to run/monitor Celery tasks.

- [ ] **Step 21**: Mark task complete.
    - *File*: `docs/system-solution/main-tasks.md`
    - *Task*: Update T003 status to complete with completion date.
