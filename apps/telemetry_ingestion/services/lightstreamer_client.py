"""Sync-to-async bridge over the official Lightstreamer client SDK.

Per ADR-002, PeeBot uses the official ``lightstreamer-client-lib`` which
is a threaded/blocking library. This module wraps it so that the
asyncio-based ingestion pipeline can receive updates via a thread-safe
callback scheduled onto the running event loop.

Three classes live here:

* :class:`SubListener` — subscription callback; forwards each update to
  the async consumer.
* :class:`StatusListener` — client-level connection state logging.
* :class:`LightstreamerClientService` — high-level facade wiring the two
  listeners into a subscription and connection to ISSLIVE.
"""

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable, Coroutine
from typing import Any, cast

from lightstreamer.client import (
    ClientListener,
    ItemUpdate,
    LightstreamerClient,
    Subscription,
    SubscriptionListener,
)

logger = logging.getLogger(__name__)

TelemetryCallback = Callable[[dict[str, dict[str, Any]]], Coroutine[Any, Any, None]]
"""Type alias for the async callback invoked per Lightstreamer update."""


class SubListener(SubscriptionListener):
    """Subscription listener that marshals updates into the asyncio loop.

    The Lightstreamer SDK invokes listener callbacks on its own worker
    threads. This class bridges to asyncio via
    :func:`asyncio.run_coroutine_threadsafe` so the consumer coroutine
    running on the main loop receives updates without thread-unsafe ORM
    access.
    """

    def __init__(
        self,
        callback: TelemetryCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Store the target coroutine callback and the event loop to use.

        Args:
            callback: Async callable to invoke per update; receives a dict
                keyed by item name.
            loop: The asyncio loop running the ingestion consumer. Must be
                open when updates arrive; updates on a closed loop are
                dropped with a warning.
        """
        self.callback = callback
        self.loop = loop

    def onItemUpdate(self, update: ItemUpdate) -> None:
        """SDK hook fired on every subscription update.

        Translates the SDK's :class:`ItemUpdate` into a plain dict and
        schedules the async ``callback`` on the target loop. Callback
        exceptions are logged (but not re-raised) so a single failing
        update cannot kill the subscription thread.
        """
        item_name = cast(str, update.getItemName())
        value = cast(dict[str, str], update.getChangedFields())

        if item_name is None or value is None:
            return

        if self.loop.is_closed():
            logger.warning("Telemetry loop closed; dropping update for %s", item_name)
            return

        received_data: dict[str, dict[str, Any]] = {item_name: value}
        future = asyncio.run_coroutine_threadsafe(
            self.callback(received_data),
            self.loop,
        )

        def _log_callback_exception(
            f: concurrent.futures.Future[Any],
        ) -> None:
            try:
                f.result()
            except Exception:
                logger.exception("Telemetry callback failed for %s", item_name)

        future.add_done_callback(_log_callback_exception)


class StatusListener(ClientListener):
    """Client-level listener that logs Lightstreamer connection state.

    Doesn't forward data — purely operational visibility so Seq / stdout
    show when the upstream connection flips state (FR-ING-001 /
    FR-ING-002 reconnection diagnostics).
    """

    def onListenStart(self) -> None:
        """Log that the SDK has begun dispatching events to this listener."""
        logger.info("Lightstreamer: Listen start")

    def onListenEnd(self) -> None:
        """Log that the SDK has stopped dispatching events to this listener."""
        logger.info("Lightstreamer: Listen end")

    def onServerError(self, code: int, message: str) -> None:
        """Log a server-side error code + message from the Lightstreamer server."""
        logger.error(f"Lightstreamer Server Error: {code} - {message}")

    def onStatusChange(self, status: str) -> None:
        """Log any state transition reported by the client (CONNECTING, DISCONNECTED, etc.)."""
        logger.info(f"Lightstreamer Status Change: {status}")


class LightstreamerClientService:
    """High-level wrapper managing the ISSLIVE subscription lifecycle.

    Constructs a single ``MERGE``-mode subscription over the configured
    PUIs, attaches :class:`SubListener` and :class:`StatusListener`, and
    exposes ``connect`` / ``disconnect`` coroutines. The SDK itself
    handles low-level reconnects internally; the
    ``run_lightstreamer`` management command wraps this service with an
    exponential-backoff loop for process-level resilience
    (FR-ING-002).
    """

    def __init__(self, item_names: list[str], callback: TelemetryCallback) -> None:
        """Configure the subscription target.

        Args:
            item_names: List of channel PUIs to subscribe to. Typically
                the keys of the in-process channel map (ADR-005).
            callback: Async callback invoked per subscription update.
        """
        self.item_names = item_names
        self.callback = callback
        self.client: LightstreamerClient | None = None

    async def connect(self) -> None:
        """Create the subscription and initiate the underlying connection.

        Subscription is configured for ``MERGE`` mode with snapshot
        delivery enabled so late subscribers receive the latest known
        value for every item. The SDK's ``setSlowingEnabled(False)``
        matches NFR-PERF-001 — we prefer dropping stale updates over
        artificially pacing the feed.
        """
        loop = asyncio.get_running_loop()
        sub = Subscription(
            mode="MERGE",
            items=self.item_names,
            fields=[
                "TimeStamp",
                "Value",
                "Status.Class",
                "Status.Indicator",
                "Status.Color",
            ],
        )
        sub.setRequestedSnapshot("yes")
        sub.addListener(SubListener(callback=self.callback, loop=loop))

        self.client = LightstreamerClient("http://push.lightstreamer.com", "ISSLIVE")
        self.client.connectionOptions.setSlowingEnabled(False)
        self.client.addListener(StatusListener())
        self.client.subscribe(sub)
        self.client.connect()

        logger.info("Lightstreamer connection initiated.")

    async def disconnect(self) -> None:
        """Tear down the subscription and clear the cached client handle."""
        if self.client:
            logger.info("Disconnecting Lightstreamer client...")
            self.client.disconnect()
            self.client = None
