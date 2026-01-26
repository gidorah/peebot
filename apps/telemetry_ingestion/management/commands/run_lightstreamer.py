import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.telemetry_ingestion.services.lightstreamer_client import (
    LightstreamerClientService,
)
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
            # Handle SIGINT if it bubbles up before async handlers catch it
            pass

    def load_channel_map(self) -> None:
        """Pre-load all TelemetryChannels into an in-memory map for fast resolution."""
        channels = TelemetryChannel.objects.values_list("public_pui", "pk")
        self.channel_map = {pui: pk for pui, pk in channels}
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
                    await self.flush_buffer(buffer)
                    buffer = []
                    last_flush_time = current_time

                # If data was retrieved, mark as done
                # Fix: We moved task_done() to flush_buffer to ensure data is persisted
                # before we tell the queue we are done.

            except asyncio.CancelledError:
                # Final flush on shutdown
                if buffer:
                    await self.flush_buffer(buffer)
                break
            except Exception as e:
                logger.error(f"Error in ingestion worker: {e}", exc_info=True)

    async def flush_buffer(self, buffer: list[dict[str, Any]]) -> None:
        """
        Transforms buffered data into TelemetryReading objects and batch inserts them.
        Implements Phase 3: Ingestion Logic & Transformation.
        """
        # CRITICAL: We MUST acknowledge every item in the buffer regardless of outcome,
        # otherwise queue.join() will hang forever.
        try:
            if not buffer:
                return

            readings: list[TelemetryReading] = []

            for item_data in buffer:
                # item_data is {pui: {field: value, ...}}
                for pui, fields in item_data.items():
                    channel_id = self.channel_map.get(pui)
                    if not channel_id:
                        # In production we might warn once per unknown channel,
                        # but for high throughput we just skip.
                        continue

                    raw_value = fields.get("Value")
                    # We strictly require a value. Status-only updates are dropped
                    # because the model requires 'value'.
                    if raw_value is None:
                        continue

                    try:
                        value = Decimal(raw_value)
                    except (InvalidOperation, TypeError):
                        logger.warning(f"Invalid value for {pui}: {raw_value}")
                        continue

                    # Timestamp handling:
                    # Source 'TimeStamp' is HOURS since the start of the current year (DOY).
                    # Example: 631.9155 hours -> Jan 26, 07:54
                    source_ts = fields.get("TimeStamp")
                    reading_ts = None

                    if source_ts:
                        try:
                            hours_from_soy = float(source_ts)
                            # Base date: Start of current year (UTC)
                            now = datetime.now(tz=UTC)
                            # ADR-010: ISS 'TimeStamp' is Hours from Dec 31 (Year-1).
                            # Fix: Base must be Jan 1 - 1 day (Dec 31).
                            base_epoch = datetime(
                                now.year, 1, 1, tzinfo=UTC
                            ) - timedelta(days=1)

                            # Add hours delta
                            reading_ts = base_epoch + timedelta(hours=hours_from_soy)

                            # Heuristic check for Year Rollover (New Year's Eve)
                            # If calculated time is > 24h in the future, it likely belongs to previous year
                            # (e.g. processing late Dec 31st data when it is already Jan 1st)
                            if reading_ts > now + timedelta(hours=24):
                                base_epoch_prev = datetime(
                                    now.year - 1, 1, 1, tzinfo=UTC
                                ) - timedelta(days=1)
                                reading_ts = base_epoch_prev + timedelta(
                                    hours=hours_from_soy
                                )
                        except (ValueError, TypeError, OverflowError) as e:
                            logger.warning(
                                f"Could not parse source timestamp '{source_ts}' for {pui}: {e}. Using now()."
                            )

                    if reading_ts is None:
                        reading_ts = timezone.now()

                    # Note: created_at and updated_at are handled by Django's bulk_create
                    # in modern versions/configurations.
                    readings.append(
                        TelemetryReading(
                            channel_id=channel_id,
                            timestamp=reading_ts,
                            value=value,
                            status_class=fields.get("Status.Class"),
                            status_indicator=fields.get("Status.Indicator"),
                            status_color=fields.get("Status.Color"),
                        )
                    )

            if readings:
                await TelemetryReading.objects.abulk_create(readings)
                logger.info(f"Flushed {len(readings)} readings to DB.")

        except Exception as e:
            logger.error(f"Error flushing buffer to DB: {e}", exc_info=True)
        finally:
            # Mark all items in this buffer as done, so the queue unblocks.
            # This happens whether the DB write succeeded or failed.
            for _ in range(len(buffer)):
                try:
                    self.queue.task_done()
                except ValueError:
                    # Ignore if called too many times (should not happen with this logic)
                    pass
