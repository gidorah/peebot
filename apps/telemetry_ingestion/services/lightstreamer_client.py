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

# Type alias for the telemetry callback
TelemetryCallback = Callable[[dict[str, dict[str, Any]]], Coroutine[Any, Any, None]]


class SubListener(SubscriptionListener):  # type: ignore[misc]
    def __init__(
        self,
        callback: TelemetryCallback,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.callback = callback
        self.loop = loop

    def onItemUpdate(self, update: ItemUpdate) -> None:
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


class StatusListener(ClientListener):  # type: ignore[misc]
    def onListenStart(self) -> None:
        logger.info("Lightstreamer: Listen start")

    def onListenEnd(self) -> None:
        logger.info("Lightstreamer: Listen end")

    def onServerError(self, code: int, message: str) -> None:
        logger.error(f"Lightstreamer Server Error: {code} - {message}")

    def onStatusChange(self, status: str) -> None:
        logger.info(f"Lightstreamer Status Change: {status}")


class LightstreamerClientService:
    def __init__(self, item_names: list[str], callback: TelemetryCallback) -> None:
        self.item_names = item_names
        self.callback = callback
        self.client: LightstreamerClient | None = None

    async def connect(self) -> None:
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
        # sub.setDataAdapter("QUOTE_ADAPTER")
        sub.setRequestedSnapshot("yes")
        sub.addListener(SubListener(callback=self.callback, loop=loop))

        self.client = LightstreamerClient("http://push.lightstreamer.com", "ISSLIVE")
        self.client.connectionOptions.setSlowingEnabled(False)
        self.client.addListener(StatusListener())
        self.client.subscribe(sub)
        self.client.connect()

        logger.info("Lightstreamer connection initiated.")

    async def disconnect(self) -> None:
        if self.client:
            logger.info("Disconnecting Lightstreamer client...")
            self.client.disconnect()
            self.client = None
