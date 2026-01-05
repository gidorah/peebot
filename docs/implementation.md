Here is the detailed, step-by-step implementation for **Option 1: The Service Coordinator Pattern**.

This approach centralizes the logic in a `Pipeline` class within your `telemetry_ingestion` module. This class orchestrates the flow while delegating specific tasks (validation, enrichment, storage) to specialized services.

### 1\. File Structure

Here is the file structure required for this implementation.

```text
apps/
├── core/
│   ├── exceptions.py          # Custom exceptions
│   └── utils.py               # Shared helpers (UUIDs, time)
├── telemetry_storage/
│   ├── models.py              # DB Models
│   └── repositories.py        # Database access layer
└── telemetry_ingestion/
    ├── serializers.py         # Validation logic
    ├── services/
    │   ├── enricher.py        # Enrichment logic
    │   └── pipeline.py        # <--- THE ORCHESTRATOR
    └── management/
        └── commands/
            └── run_lightstreamer.py
```

-----

### 2\. The Core (Shared Utilities)

First, define a specific exception so your pipeline knows when to gracefully skip bad data.

```python
# apps/core/exceptions.py
class TelemetryValidationError(Exception):
    """Raised when incoming data fails validation rules."""
    pass
```

-----

### 3\. The Storage Module (Repository Layer)

Your ingestion module needs a way to talk to the database without touching models directly.

```python
# apps/telemetry_storage/repositories.py
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from .models import TelemetryReading, TelemetryChannel

class TelemetryRepository:
    """
    Handles all DB interactions. 
    Using sync_to_async or native async methods provided by Django 5.x.
    """
    
    async def get_or_create_channel(self, item_id: str) -> TelemetryChannel:
        # Django 5+ supports aget_or_create
        # Use all_objects to check for soft-deleted channels
        channel, created = await TelemetryChannel.all_objects.aget_or_create(
            public_pui=item_id,
            defaults={'deleted_at': None}
        )
        return channel

    async def save_reading(self, reading_data: dict) -> TelemetryReading:
        """
        Persists a single reading.
        Expects reading_data to contain 'channel_id' (FK) not string item_id.
        """
        try:
            # Use acreate for async insert
            return await TelemetryReading.objects.acreate(**reading_data)
        except IntegrityError as e:
            # Handle duplicate event_id if necessary
            raise e
```

-----

### 4\. The Ingestion Module (Components)

Now we build the components that the orchestrator will control.

#### A. Validator (Serializer)

Uses DRF to ensure data integrity.

```python
# apps/telemetry_ingestion/serializers.py
from rest_framework import serializers
from apps.core.exceptions import TelemetryValidationError

class LightstreamerReadingSerializer(serializers.Serializer):
    # Mapping raw Lightstreamer fields (e.g., 'f_1') to internal names
    item = serializers.CharField(source='item_id') 
    f_1 = serializers.DecimalField(source='value', max_digits=10, decimal_places=4)
    # Add other fields as necessary...

    def validate_value(self, value):
        if value < 0:
            # Example business rule
            raise serializers.ValidationError("Value cannot be negative")
        return value

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError as e:
            # Re-raise as our custom exception to keep the pipeline clean
            raise TelemetryValidationError(e.detail)
```

#### B. Enricher

Adds system-generated metadata.

```python
# apps/telemetry_ingestion/services/enricher.py
import uuid
from django.utils import timezone

class EnrichmentService:
    def enrich(self, validated_data: dict) -> dict:
        """
        Adds metadata to the clean data.
        """
        # Create a copy to avoid mutating original data
        data = validated_data.copy()
        
        # 1. Add Traceability
        data['id'] = uuid.uuid4()  # Will be UUIDv7 in production
        
        # 2. Add Ingestion Timestamp (Server Time)
        data['created_at'] = timezone.now()
        
        # 3. Any other normalization (e.g., unit conversion)
        # data['value'] = data['value'] * 100 
        
        return data
```

-----

### 5\. The Orchestrator (The Coordinator)

This is the most important part of Option 1. It wires everything together.

```python
# apps/telemetry_ingestion/services/pipeline.py
import logging
from apps.core.exceptions import TelemetryValidationError
from apps.telemetry_storage.repositories import TelemetryRepository
from ..serializers import LightstreamerReadingSerializer
from .enricher import EnrichmentService

logger = logging.getLogger(__name__)

class IngestionPipeline:
    def __init__(self):
        # Initialize dependencies once
        self.enricher = EnrichmentService()
        self.repository = TelemetryRepository()

    async def process_message(self, raw_message: dict):
        """
        The main entry point. Orchestrates the flow:
        Raw -> Validate -> Enrich -> Persist
        """
        try:
            # --- STEP 1: VALIDATION ---
            serializer = LightstreamerReadingSerializer(data=raw_message)
            if not serializer.is_valid():
                raise TelemetryValidationError(serializer.errors)
            
            clean_data = serializer.validated_data
            item_id = clean_data.pop('item_id') # Extract ID to look up channel

            # --- STEP 2: CHANNEL RESOLUTION ---
            # We need the actual Channel Object/ID, not just the string name
            channel = await self.repository.get_or_create_channel(item_id)
            clean_data['channel'] = channel

            # --- STEP 3: ENRICHMENT ---
            final_data = self.enricher.enrich(clean_data)

            # --- STEP 4: PERSISTENCE ---
            await self.repository.save_reading(final_data)
            
            # Optional: Log success (debug level to avoid spam)
            logger.debug(f"Saved reading for {item_id}: {final_data['event_id']}")

        except TelemetryValidationError as e:
            logger.warning(f"Skipping malformed message: {e}")
        except Exception as e:
            # Catch-all for unexpected DB errors or code bugs
            logger.error(f"Pipeline failed processing message {raw_message}: {e}", exc_info=True)
```

-----

### 6\. The Entry Point (Management Command)

Finally, how you call it from your long-running command.

```python
# apps/telemetry_ingestion/management/commands/run_lightstreamer.py
import asyncio
from django.core.management.base import BaseCommand
from apps.telemetry_ingestion.services.pipeline import IngestionPipeline

# Mock Lightstreamer Client for demonstration
class LightstreamerClient:
    def __init__(self, callback):
        self.callback = callback

    async def connect(self):
        print("Connected to ISS Lightstreamer...")
        # Simulating incoming data stream
        simulated_data = [
            {"item": "NODE3000004", "f_1": "10.5"},
            {"item": "NODE3000004", "f_1": "11.2"},
            {"item": "BAD_DATA_TEST", "f_1": "-5"}, # Will fail validation
        ]
        
        for msg in simulated_data:
            await asyncio.sleep(0.5) # Simulate network delay
            await self.callback(msg)

class Command(BaseCommand):
    help = 'Starts the ISS Lightstreamer ingestion client'

    def handle(self, *args, **options):
        # Django management commands are synchronous by default.
        # We need to run the async loop manually.
        asyncio.run(self.run_async())

    async def run_async(self):
        # 1. Instantiate the Orchestrator
        pipeline = IngestionPipeline()

        # 2. Define the callback that bridges Client -> Pipeline
        async def on_message_received(message):
            # This AWAITS the pipeline. The client will not process 
            # the next message until this line finishes.
            await pipeline.process_message(message)

        # 3. Start the Client
        client = LightstreamerClient(callback=on_message_received)
        await client.connect()
```

### Why this works for you

1.  **Testability:** You can easily write a unit test for `IngestionPipeline` by mocking the `repository` and `serializer`.
2.  **Clarity:** If data isn't being saved, you look at `process_message`. The flow is obvious.
3.  **Safety:** By using `await` at every step, you ensure you don't lose data in a background thread if the process crashes. The processing of message A is confirmed before message B starts.