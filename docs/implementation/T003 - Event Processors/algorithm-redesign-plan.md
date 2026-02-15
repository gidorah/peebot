# T003 Algorithm Redesign Plan

**Date:** 2026-02-15
**Trigger:** Data analysis report revealed fundamental flaws in PeeBotProcessor
**Scope:** `apps/event_processors/processors/pee_bot.py`, tests, tasks, docs

---

## Problem Summary

The current `PeeBotProcessor` cannot detect real urination events due to 4 compounding issues:

| # | Issue | Current | Required |
|---|-------|---------|----------|
| 1 | **Wrong channel** | `NODE3000004` (UPA state enum) | `NODE3000005` (WSTA tank qty %) |
| 2 | **Broken detection paradigm** | Strictly monotonic burst detection | Net-change-over-window |
| 3 | **Wrong duration thresholds** | 30–120s | 10–30s (real fills are 10–25s) |
| 4 | **Wrong delta threshold** | 0.5 (continuous) | 2 (integer %, noise-immune) |

Root cause: The algorithm was designed against assumed sensor behavior. Real data shows integer-only percentage values with ±1% noise bounces that shatter any monotonic-rise detector.

---

## Step-by-Step Implementation Plan

### Step 1: Update Channel PUI Configuration

**File:** `apps/event_processors/processors/pee_bot.py`

Change `channel_pui` from `NODE3000004` to `NODE3000005`.

```python
# Before
channel_pui = "NODE3000004"

# After
channel_pui = "NODE3000005"
```

**Ripple effects:**
- Update `DetectedEvent.channel_id` references in test fixtures
- Update docstrings referencing `NODE3000004`
- Update `design.md` section 4.4 channel reference

---

### Step 2: Replace Burst Detection with Net-Change-Over-Window Algorithm

**File:** `apps/event_processors/processors/pee_bot.py`

The current `_detect_bursts()` method walks readings looking for strictly monotonic rises. This fundamentally cannot work because real sensor data has ±1% noise bounces mid-fill:

```
Real fill: 19 → 20 → 21 → 20 → 21  (net +2%, but not monotonic)
Current algo: burst starts at 19→20, BREAKS at 21→20, only 2 readings
```

**New algorithm — `_detect_fill_events()`:**

```
For the sorted readings window:
  1. Slide a 30-second window across the readings
  2. At each position: net_change = window_end_value - window_start_value
  3. If net_change >= NET_DELTA_THRESHOLD (+2%):
     → Candidate fill event found
  4. Validate with stability check:
     - Look 30-60s after the window end
     - Confirm level stays ≥ (peak - 1%) — sustained elevation
  5. If stable → return FillEvent with metadata
```

**Why this works:**
- ±1% bounces within a +3% rise cancel out — net change still ≥ +2%
- The 30s window captures the full 10–25s fill event with margin
- Stability check rejects noise oscillation (e.g., 50% ↔ 51%)

**New dataclass to replace `BurstInfo`:**

```python
@dataclass
class FillEvent:
    """A detected tank fill event based on net change over a window."""
    window_start_time: datetime
    window_end_time: datetime
    start_value: Decimal
    end_value: Decimal
    peak_value: Decimal
    net_delta: Decimal
    readings_in_window: int

    @property
    def duration_seconds(self) -> float:
        return (self.window_end_time - self.window_start_time).total_seconds()
```

---

### Step 3: Update Detection Thresholds

**File:** `apps/event_processors/processors/pee_bot.py`

Replace the current threshold constants:

```python
# REMOVE these:
MIN_BURST_DURATION_SECONDS = 30.0
MAX_BURST_DURATION_SECONDS = 120.0
STABILITY_CHECK_SECONDS = 15.0
GLITCH_REVERSION_SECONDS = 15.0
MIN_DELTA_THRESHOLD = Decimal("0.5")

# ADD these (data-driven values from analysis report):
DETECTION_WINDOW_SECONDS = 30       # Slide window size (captures 10-25s fill + margin)
NET_DELTA_THRESHOLD = Decimal("2")  # Minimum net rise to qualify (filters ±1% noise)
STABILITY_WINDOW_SECONDS = 60       # Post-fill stability check duration
STABILITY_TOLERANCE = Decimal("1")  # Max allowed drop during stability (±1% noise OK)
```

**Rationale from data analysis:**

| Parameter | Value | Evidence |
|-----------|-------|----------|
| Window: 30s | Captures full fill event (10–25s real duration) with margin |
| Min delta: +2% | All confirmed fills show +2% to +3%. Noise is ±1% only |
| Stability: 60s | Post-fill level must hold. Rejects 50%↔51% oscillation |
| Tolerance: 1% | Allows normal ±1% sensor jitter post-fill |

---

### Step 4: Rewrite `analyze()` Method

**File:** `apps/event_processors/processors/pee_bot.py`

The new `analyze()` orchestration:

```python
async def analyze(self, readings: list[TelemetryReading]) -> DetectionResult | None:
    if len(readings) < 3:
        return None

    sorted_readings = sorted(readings, key=lambda r: r.timestamp)

    # Step 1: Detect fill event candidates using net-change-over-window
    fill_event = self._detect_fill_event(sorted_readings)

    if fill_event is None:
        return None

    # Step 2: Validate with post-fill stability check
    if not self._check_stability(fill_event, sorted_readings):
        return None

    # Step 3: Calculate confidence
    confidence = self.get_confidence(sorted_readings)

    return DetectionResult(
        event_type="urination",
        detected_at=fill_event.window_start_time,
        confidence=confidence,
        metadata={...fill event details...},
    )
```

---

### Step 5: Implement `_detect_fill_event()` Method

**File:** `apps/event_processors/processors/pee_bot.py`

Core sliding-window algorithm:

```
def _detect_fill_event(readings) -> FillEvent | None:
    for each reading as window_start:
        window_end_time = window_start.timestamp + DETECTION_WINDOW_SECONDS
        window_readings = readings within [window_start, window_end_time]

        if len(window_readings) < 2:
            continue

        start_val = window_readings[0].value
        end_val = window_readings[-1].value
        net_delta = end_val - start_val
        peak_val = max(r.value for r in window_readings)

        if net_delta >= NET_DELTA_THRESHOLD:
            return FillEvent(
                window_start_time=window_readings[0].timestamp,
                window_end_time=window_readings[-1].timestamp,
                start_value=start_val,
                end_value=end_val,
                peak_value=peak_val,
                net_delta=net_delta,
                readings_in_window=len(window_readings),
            )

    return None
```

**Key design decisions:**
- Returns the **first** fill event found (earliest in time)
- Uses `value` field (not `calibrated_data` — analysis shows 0% calibrated coverage)
- The window slides by reading, not by fixed time step — adapts to irregular data

---

### Step 6: Rewrite `_check_stability()` Method

**File:** `apps/event_processors/processors/pee_bot.py`

Renamed from `_check_post_burst_stability()`. New logic:

```
def _check_stability(fill_event, all_readings) -> bool:
    # Find readings in [fill_end, fill_end + STABILITY_WINDOW_SECONDS]
    stability_readings = readings after fill_event.window_end_time
                         within STABILITY_WINDOW_SECONDS

    if len(stability_readings) < 1:
        # No post-fill data — conservatively accept
        return True

    # Check that ALL stability readings stay ≥ (end_value - STABILITY_TOLERANCE)
    floor = fill_event.end_value - STABILITY_TOLERANCE

    for reading in stability_readings:
        if reading.value < floor:
            return False  # Level dropped too much — noise oscillation, not fill

    return True
```

**Why this replaces the old approach:**
- Old: calculated rate-of-change per minute with complex thresholds
- New: simple floor check — did the level stay elevated? Yes/No
- Directly matches the data pattern: real fills sustain, noise reverts

---

### Step 7: Remove Dead Code

**File:** `apps/event_processors/processors/pee_bot.py`

Remove methods that are no longer needed:
- `_detect_bursts()` — replaced by `_detect_fill_event()`
- `_is_valid_burst_duration()` — duration validation is now implicit in window size
- `_is_glitch()` — net-change approach inherently filters glitches
- `BurstInfo` dataclass — replaced by `FillEvent`

---

### Step 8: Simplify `get_confidence()` Method

**File:** `apps/event_processors/processors/pee_bot.py`

Current confidence uses R², SNR, and sample density — designed for smooth continuous signals. With integer data, these metrics are less meaningful.

**New confidence model:**

```python
def get_confidence(self, readings, fill_event) -> Decimal:
    """Confidence based on:
    - Delta magnitude: +2% = 0.6 base, +3% = 0.8, +4% = 0.9
    - Stability: how long level holds post-fill (more data = more confident)
    - Reading density: more readings in window = more reliable
    """
    # Delta component (40% weight)
    delta_score = min(float(fill_event.net_delta) / 4.0, 1.0)

    # Stability component (30% weight)
    # Based on how many stability readings confirm elevation
    stability_score = min(stability_readings_count / 5.0, 1.0)

    # Density component (30% weight)
    density_score = min(fill_event.readings_in_window / 6.0, 1.0)

    raw = delta_score * 0.4 + stability_score * 0.3 + density_score * 0.3
    return Decimal(str(round(max(0.0, min(1.0, raw)), 2)))
```

**Design note:** The `get_confidence()` signature changes — it now takes the `FillEvent` as context. The `BaseProcessor` abstract method signature should be updated or the implementation should adapt internally.

---

### Step 9: Update `_query_readings()` in tasks.py

**File:** `apps/event_processors/tasks.py`

The current `_query_readings()` is fine architecturally but references `processor.channel_pui` — which will automatically pick up the new `NODE3000005` value. No structural changes needed, but verify:

- The query uses `channel__public_pui=processor.channel_pui` — correct
- Window overlap of 30s for context — still appropriate
- `window_minutes` stays at 10 (provides 10-min context for stability)

**One potential adjustment:** Consider reducing `window_minutes` from 10 to 5. The fill + stability check only needs ~90s total (30s detection + 60s stability). But 5 minutes provides extra context and is not expensive. **Keep at 5–10 minutes.**

---

### Step 10: Rewrite All Unit Tests

**File:** `apps/event_processors/tests/test_pee_bot.py`

All existing tests are built around the monotonic burst paradigm and must be rewritten for the net-change-over-window algorithm.

**New test categories:**

#### 10a. Configuration Tests
```
- test_channel_pui_is_NODE3000005
- test_detection_thresholds_match_data_analysis
```

#### 10b. Fill Event Detection (Happy Path)
```
- test_clear_fill_event_detected
  Simulate: 19→20→21→22 over 15s, then stable at 22 for 60s → event detected

- test_fill_event_with_noise_bounce_detected
  Simulate: 19→20→21→20→21→22 over 20s (±1% mid-fill), stable at 22 → detected
  THIS IS THE CRITICAL TEST — the exact pattern that broke the old algorithm

- test_three_percent_fill_detected
  Simulate: 27→28→29→30 over 17s, stable at 30 → detected with higher confidence
```

#### 10c. Noise Rejection (False Positive Prevention)
```
- test_boundary_oscillation_rejected
  Simulate: 50→51→50→51→50→51 over 60s → no event (net change ≤1%)

- test_single_step_noise_rejected
  Simulate: 20→21→20 over 5s → no event (net change 0, or +1 < threshold)

- test_drain_with_noise_rejected
  Simulate: 22→21→22→21→20→19 (declining trend with bounces) → no event
```

#### 10d. Stability Validation
```
- test_fill_without_stability_data_accepted
  Simulate: fill event at end of window, no post-fill readings → conservatively accept

- test_fill_that_reverts_rejected
  Simulate: 19→21 (+2%), then drops to 19 within 30s → rejected (level didn't hold)

- test_fill_with_slow_drain_accepted
  Simulate: 19→21, then slowly 21→20 over 60s → accepted (UPA processing)
```

#### 10e. Edge Cases
```
- test_empty_readings_no_event
- test_insufficient_readings_no_event
- test_unsorted_readings_handled
- test_flat_readings_no_event
- test_all_same_value_no_event
```

#### 10f. Confidence Calculation
```
- test_higher_delta_higher_confidence
- test_more_stability_readings_higher_confidence
- test_confidence_range_valid
```

---

### Step 11: Update Integration Tests

**File:** `tests/test_event_processors_integration.py`

Update fixtures to:
- Use `NODE3000005` channel PUI
- Generate integer percentage readings (not smooth continuous values)
- Include ±1% noise patterns in test data
- Verify the end-to-end flow: readings → detection → DetectedEvent creation

---

### Step 12: Update Documentation

**Files to update:**

| File | Changes |
|------|---------|
| `apps/event_processors/processors/pee_bot.py` | Module docstring: new algorithm description |
| `apps/event_processors/AGENTS.md` | Update channel reference |
| `docs/implementation/T003 - Event Processors/design.md` | Section 4.4: new algorithm, new thresholds, new channel |
| `docs/implementation/T003 - Event Processors/tasks.md` | Add Phase 10 for algorithm redesign steps |

---

### Step 13: Update `DetectedEvent.channel_id` Default in Models

**File:** `apps/event_processors/models.py`

The `channel_id` field has no default — it's set by the processor at event creation time. The value will automatically change because `PeeBotProcessor.channel_pui` changes. No model migration needed.

Verify: `help_text` on `channel_id` references `NODE3000004` as an example — update to `NODE3000005`.

---

## Execution Order & Dependencies

```
Step 1  (channel PUI)           ─── standalone, do first
Step 2  (FillEvent dataclass)   ─── standalone
Step 3  (thresholds)            ─── standalone
Step 7  (remove dead code)      ─── after steps 4-6
Step 4  (analyze rewrite)       ─── depends on 2, 3
Step 5  (detect_fill_event)     ─── depends on 2, 3
Step 6  (stability rewrite)     ─── depends on 2, 3
Step 8  (confidence)            ─── depends on 2
Step 9  (tasks.py check)        ─── after step 1
Step 10 (unit tests)            ─── after steps 4-8
Step 11 (integration tests)     ─── after step 10
Step 12 (docs)                  ─── after all code complete
Step 13 (model help_text)       ─── standalone, minor
```

**Suggested batch order:**
1. **Batch A** (Steps 1, 2, 3, 13): Config + data structures — no behavior change yet
2. **Batch B** (Steps 4, 5, 6, 7, 8): Core algorithm rewrite — all at once since they're tightly coupled
3. **Batch C** (Steps 9, 10, 11): Testing — verify everything works
4. **Batch D** (Step 12): Documentation

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| New algorithm has different false-positive rate | Thresholds derived from real data. Can tune `NET_DELTA_THRESHOLD` if needed |
| Limited training data (128 readings) | Conservative defaults. Log all near-threshold events for manual review |
| Fill during active UPA drain might cancel out | Accept as known limitation. Document in metadata. May need longer window if draining |
| `calibrated_data` becomes available later | Keep fallback: `reading.calibrated_data or reading.value`. Currently 0% coverage |
| BaseProcessor.get_confidence signature tension | Pass FillEvent data internally within PeeBotProcessor, keep BaseProcessor interface stable |

---

## Validation Criteria

The redesign is complete when:

1. `just test` passes with all new and updated tests
2. `uv run mypy apps/` passes with no new errors
3. PeeBotProcessor targets `NODE3000005`
4. The fill-with-noise-bounce test passes (the specific pattern that broke the old algorithm)
5. Boundary oscillation (50%↔51%) is correctly rejected
6. Documentation reflects the new algorithm
