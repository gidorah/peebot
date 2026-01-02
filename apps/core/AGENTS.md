# AGENT CONTEXT: CORE MODULE

**Role**: Foundation for all apps. Abstract bases & shared utilities. No business logic.

## BASE MODELS (`models.py`)
- `TimeStampedModel`: Adds `created_at` (auto_add) and `updated_at` (auto).
- `UUIDModel`: Replaces PK with `id` (UUID4, non-editable).
- `SoftDeleteModel`: Implements `deleted_at`.
  - `soft_delete()` / `restore()`.
  - `objects`: Filters active. `all_objects`: All records.

## EXCEPTIONS (`exceptions.py`)
- `TelemetryError`: Root exception.
- Subclasses: `ValidationError`, `EnrichmentError`, `IngestionError`, `ProcessorError`.

## UTILITIES (`utils.py`)
- `generate_event_id()`: Returns UUID4 for tracking.
- Placeholders: `normalize_timestamp`, `safe_decimal`, `chunk_list`.

## SERIALIZERS (`serializers.py`)
- `BaseTelemetrySerializer`: Shared DRF base.

## LAWS
1. NEVER add domain-specific logic here.
2. Abstract models MUST set `abstract = True`.
3. All feature modules MUST inherit from these bases for consistency.
