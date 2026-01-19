import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast

from lightstreamer.client import (
    ItemUpdate,
    LightstreamerClient,
    Subscription,
    SubscriptionListener,
)

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

        received_data: dict[str, dict[str, Any]] = {item_name: value}
        asyncio.run_coroutine_threadsafe(self.callback(received_data), self.loop)


class LightstreamerClientService:
    def __init__(self, item_names: list[str], callback: TelemetryCallback) -> None:
        self.item_names = item_names
        self.callback = callback

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

        client = LightstreamerClient("http://push.lightstreamer.com", "ISSLIVE")
        client.connectionOptions.setSlowingEnabled(False)
        client.subscribe(sub)
        client.connect()

        print("Lightstreamer connected.")
