import asyncio
import logging
from typing import Any

from django.core.management.base import BaseCommand

from apps.telemetry_ingestion.services.lightstreamer_client import (
    LightstreamerClientService,
)
from apps.telemetry_storage.models import TelemetryChannel

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Starts the ISS Lightstreamer ingestion client"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.channel_map: dict[str, Any] = {}
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=50000)

    def handle(self, *args: Any, **options: Any) -> None:
        asyncio.run(self.run_async())

    def load_channel_map(self) -> None:
        """Pre-load all TelemetryChannels into an in-memory map for fast resolution."""
        channels = TelemetryChannel.objects.all()
        # Use .pk to avoid LSP ambiguity with id attribute
        self.channel_map = {c.public_pui: c.pk for c in channels}
        logger.info(f"Loaded {len(self.channel_map)} channels into memory map.")

    async def run_async(self) -> None:
        # Step 1: Load channel map (ADR-005)
        self.load_channel_map()

        if not self.channel_map:
            logger.error("No channels found in database. Please seed channels first.")
            return

        item_names = list(self.channel_map.keys())

        async def on_data_received(incoming_data: dict[str, dict[str, Any]]) -> None:
            """Callback for Lightstreamer updates. Pushes to queue with backpressure."""
            try:
                # incoming_data is {item_name: {field: value}}
                self.queue.put_nowait(incoming_data)
            except asyncio.QueueFull:
                logger.warning("Ingestion queue full! Dropping oldest message.")
                try:
                    self.queue.get_nowait()
                    self.queue.put_nowait(incoming_data)
                except asyncio.QueueEmpty:
                    pass

        # Step 2: Initialize Client with PUIs from DB
        client = LightstreamerClientService(
            item_names=item_names, callback=on_data_received
        )

        # Step 3: Start Tasks
        worker_task = asyncio.create_task(self.ingestion_worker())

        try:
            await client.connect()
            # Keep running until cancelled
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Command cancelled, shutting down...")
        finally:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            logger.info("Ingestion process stopped.")

    async def ingestion_worker(self) -> None:
        """
        Consumer task that processes messages from the queue with buffering logic.
        Flushes when buffer reaches 2000 items OR after 500ms (ADR-002, ADR-003).
        """
        logger.info("Ingestion worker started.")
        buffer: list[dict[str, Any]] = []
        last_flush_time = asyncio.get_event_loop().time()

        # Buffering constraints from requirements
        MAX_BUFFER_SIZE = 2000
        MAX_FLUSH_INTERVAL = 0.5  # seconds

        while True:
            try:
                # Wait for an item with a timeout to handle the periodic flush
                try:
                    data = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    buffer.append(data)
                except TimeoutError:
                    pass

                current_time = asyncio.get_event_loop().time()
                time_since_flush = current_time - last_flush_time

                # Check if we should flush
                if len(buffer) >= MAX_BUFFER_SIZE or (
                    buffer and time_since_flush >= MAX_FLUSH_INTERVAL
                ):
                    await self.flush_buffer_placeholder(buffer)
                    buffer = []
                    last_flush_time = current_time

                # If data was retrieved, mark as done
                try:
                    self.queue.task_done()
                except ValueError:  # If get() didn't happen
                    pass

            except asyncio.CancelledError:
                # Final flush on shutdown
                if buffer:
                    await self.flush_buffer_placeholder(buffer)
                break
            except Exception as e:
                logger.error(f"Error in ingestion worker: {e}", exc_info=True)

    async def flush_buffer_placeholder(self, buffer: list[dict[str, Any]]) -> None:
        """Placeholder for Phase 3: Transformation and Batch Write."""
        logger.debug(f"Buffering logic triggered: Flushing {len(buffer)} items.")
        # This will be implemented in Phase 3
        pass
