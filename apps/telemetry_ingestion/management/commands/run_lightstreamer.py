import asyncio
import logging
import signal
from typing import Any

from django.core.management.base import BaseCommand

from apps.telemetry_ingestion.services.enricher import TelemetryEnricher
from apps.telemetry_ingestion.services.lightstreamer_client import (
    LightstreamerClientService,
)
from apps.telemetry_ingestion.services.validator import validate_payload
from apps.telemetry_storage.models import TelemetryChannel, TelemetryReading

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Starts the ISS Lightstreamer ingestion client"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.channel_map: dict[str, Any] = {}
        # Queue initialized in run_async to ensure loop attachment
        self.queue: asyncio.Queue[dict[str, Any]]

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            logger.info("User interrupted process via KeyboardInterrupt.")

    def load_channel_map(self) -> None:
        """Pre-load all TelemetryChannels into an in-memory map for fast resolution."""
        channels = TelemetryChannel.objects.values_list("public_pui", "pk")
        self.channel_map = dict(channels)
        logger.info(f"Loaded {len(self.channel_map)} channels into memory map.")

    async def run_async(self) -> None:
        # Step 0: Initialize Queue in the running loop
        self.queue = asyncio.Queue(maxsize=50000)

        # Step 1: Load channel map (ADR-005)
        # We need to wrap the sync DB access in sync_to_async
        from asgiref.sync import sync_to_async

        await sync_to_async(self.load_channel_map)()

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

        # Step 3: Setup Shutdown Signal Handling
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _signal_handler() -> None:
            logger.info("Signal received, initiating shutdown...")
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                # Fallback for loops that don't support signal handlers (e.g. some tests)
                logger.warning(f"Signal handlers not implemented for loop {type(loop)}")

        # Step 4: Start Worker and Connection Loop
        worker_task = asyncio.create_task(self.ingestion_worker())
        attempt = 0

        logger.info("Starting ingestion loop...")

        while not shutdown_event.is_set():
            try:
                logger.info(f"Connecting to Lightstreamer (Attempt {attempt + 1})...")
                await client.connect()

                # Reset attempt counter on successful initiation
                attempt = 0

                # Wait until shutdown is signaled
                # Note: If the client library loses connection, it usually retries internally.
                # If it raises an exception during connect, we catch it below.
                await shutdown_event.wait()

            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    break

                logger.error(f"Connection failed or lost: {e}")
                attempt += 1
                # Exponential backoff: 1s, 2s, 4s... max 60s
                delay = min(60, 2 ** (attempt - 1)) if attempt > 0 else 1
                logger.info(f"Retrying in {delay} seconds...")

                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
                except TimeoutError:
                    continue  # Retry connection
                except asyncio.CancelledError:
                    break  # Exit loop

        # Step 5: Graceful Shutdown
        logger.info("Shutting down resources...")
        await client.disconnect()

        # Drain Queue: Wait for worker to process remaining items
        logger.info("Draining ingestion queue...")
        try:
            # We assume the producer (client) is stopped, so no new items.
            # wait_for join() ensures we process what's left.
            if not self.queue.empty():
                await asyncio.wait_for(self.queue.join(), timeout=10.0)
        except TimeoutError:
            logger.warning("Queue drain timed out! Some items may be lost.")
        except Exception as e:
            logger.error(f"Error draining queue: {e}")

        # Cancel worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            logger.info("Worker task cancelled.")

        logger.info("Ingestion process stopped.")

    async def ingestion_worker(self) -> None:
        """
        Consumer task that processes messages from the queue with buffering logic.
        Flushes when buffer reaches 2000 items OR after 500ms (ADR-002, ADR-003).
        """
        logger.info("Ingestion worker started.")
        buffer: list[dict[str, Any]] = []
        pending_queue_count = 0  # Number of raw queue items to acknowledge
        last_flush_time = asyncio.get_event_loop().time()

        # Buffering constraints from requirements
        MAX_BUFFER_SIZE = 2000
        MAX_FLUSH_INTERVAL = 0.5  # seconds

        while True:
            try:
                # Wait for an item with a timeout to handle the periodic flush
                try:
                    data = await asyncio.wait_for(self.queue.get(), timeout=0.1)

                    # Process the raw item immediately (Validation + Enrichment)
                    # data is {pui: {field: value, ...}}
                    for pui, fields in data.items():
                        # 1. Validate
                        validated_reading = validate_payload(pui, fields)
                        if not validated_reading:
                            # dropped invalid data
                            continue

                        # 2. Enrich
                        enriched_data = TelemetryEnricher.enrich(validated_reading)
                        buffer.append(enriched_data)

                    pending_queue_count += 1

                except TimeoutError:
                    pass

                current_time = asyncio.get_event_loop().time()
                time_since_flush = current_time - last_flush_time

                # Check if we should flush
                if len(buffer) >= MAX_BUFFER_SIZE or (
                    pending_queue_count > 0 and time_since_flush >= MAX_FLUSH_INTERVAL
                ):
                    # Flush the enriched buffer AND acknowledge the queue items
                    await self.flush_buffer(buffer, pending_queue_count)
                    buffer = []
                    pending_queue_count = 0
                    last_flush_time = current_time

            except asyncio.CancelledError:
                # Final flush on shutdown
                if buffer or pending_queue_count > 0:
                    await self.flush_buffer(buffer, pending_queue_count)
                break
            except Exception as e:
                logger.error(f"Error in ingestion worker: {e}", exc_info=True)
                # If we crash, we should try to ack pending items to prevent deadlock on join()
                # though usually we just loop.
                # Ideally we don't crash the loop.

    async def flush_buffer(
        self, buffer: list[dict[str, Any]], queue_items_to_ack: int
    ) -> None:
        """
        Transforms enriched data into TelemetryReading objects and batch inserts them.
        Uses abulk_create for performance.
        """
        try:
            if not buffer:
                return

            readings: list[TelemetryReading] = []

            for item in buffer:
                # item is validated and enriched dict
                # We just need to map channel_id and instantiate
                pui = item["pui"]
                channel_id = self.channel_map.get(str(pui))

                if not channel_id:
                    # Should be rare if channel_map is up to date
                    logger.info(
                        f"Incoming PUI {pui} is not in the channel map. Ignoring the reading."
                    )
                    continue

                readings.append(
                    TelemetryReading(
                        channel_id=channel_id,
                        timestamp=item["timestamp"],
                        value=item["value"],
                        status_class=item.get("status_class"),
                        status_indicator=item.get("status_indicator"),
                        status_color=item.get("status_color"),
                    )
                )

            if readings:
                await TelemetryReading.objects.abulk_create(readings)
                logger.info(
                    f"Flushed {len(readings)} readings to DB (Acked {queue_items_to_ack} queue items)."
                )
            else:
                logger.debug(
                    f"Buffer processed but no readings created (Acked {queue_items_to_ack} queue items)."
                )

        except Exception as e:
            logger.error(f"Error flushing buffer to DB: {e}", exc_info=True)
        finally:
            # CRITICAL: We MUST acknowledge every item pulled from the queue
            # regardless of outcome, otherwise queue.join() will hang forever.
            for _ in range(queue_items_to_ack):
                try:
                    self.queue.task_done()
                except ValueError:
                    logger.warning("queue.task_done() called too many times.")
