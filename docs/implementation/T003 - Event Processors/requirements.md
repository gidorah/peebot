# Requirements: T003 - Event Processors

## 1. Goal
Implement an analytics framework that detects ISS operational events and triggers automated social media engagement.

## 2. Functional Requirements

### 2.1 Polling Framework (FR-PROC-001)
1. The system shall execute analytics modules independently via periodic polling.
2. Each processor shall run on its own configurable schedule.
3. The system shall not use event streaming infrastructure for analytics data flow.

### 2.2 PeeBot Processor (FR-PROC-002, FR-PROC-003)
1. The processor shall poll for new data on channel `NODE3000004` (UPA Tank Level) every 30 seconds.
2. The processor shall detect a "Fill Event" when the tank level shows a sustained increase (burst) lasting 30 seconds to 2 minutes, distinguishing real fills from sensor glitches.
3. The processor shall reject glitches where the level immediately reverts to baseline after a spike.
4. The processor shall persist its processing state to support resumption after restarts.

### 2.3 Joke Generation (FR-PROC-004)
1. Upon detecting an event, the system shall generate humorous text with a "dry, scientific, slightly absurd" tone.
2. The system shall use an external LLM API for text generation.

### 2.4 Social Media Posting (FR-PROC-005)
1. The system shall post generated text to Bluesky automatically.
2. The system shall track all social media posts separately from detected events.
3. The system shall enforce a minimum 30-minute cooldown between posts.
4. The system shall comply with Bluesky AT Protocol rate limits.

## 3. Non-Functional Requirements

### 3.1 Performance (NFR-PERF-004)
1. Detection latency (event occurrence to detection) shall be < 2 minutes.

### 3.2 Architecture (NFR-ARCH-001, NFR-ARCH-002)
1. The module shall own `DetectedEvent`, `ProcessorState`, and `SocialPost` models.
2. The module shall query `TelemetryReading` from `telemetry_storage`; it shall not define its own telemetry models.
3. TimescaleDB shall be the only persistent store for analytics state and results.

### 3.3 Reliability (NFR-REL-002)
1. Processors shall persist state (`last_processed_timestamp`) to allow resumption after failures.
2. Processors shall support historical replay by adjusting the `last_processed_timestamp` value.

## 4. Constraints
1. No Kafka or complex event streaming infrastructure (C-003).
2. Bluesky API usage must respect AT Protocol rate limits (C-004).

## 5. Assumptions
1. The LLM provider will be selected during implementation; architecture must support provider swaps (A-002).
