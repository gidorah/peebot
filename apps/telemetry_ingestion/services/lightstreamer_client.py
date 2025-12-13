from typing import Any
import asyncio

from lightstreamer.client import LightstreamerClient, Subscription, SubscriptionListener
from lightstreamer.client.ls_python_client_haxe import (
    com_lightstreamer_client_internal_update_ItemUpdateBase as ItemUpdate,
)
from apps.telemetry_ingestion.services.identifiers import IDENTIFIERS


class SubListener(SubscriptionListener):  # type: ignore[misc]
    def __init__(
        self,
        callback: Any,
        loop: asyncio.AbstractEventLoop,
        subscribed_items: list[str],
    ) -> None:
        self.callback = callback
        self.loop = loop
        self.subscribed_items = subscribed_items

    def onItemUpdate(self, update: ItemUpdate) -> None:
        item_name = update.getItemName()
        if item_name not in self.subscribed_items:
            return

        value = update.getChangedFields()
        received_data = {item_name: value}
        asyncio.run_coroutine_threadsafe(self.callback(received_data), self.loop)


SUBS = IDENTIFIERS


class LightstreamerClientService:
    def __init__(self, callback: Any) -> None:
        self.callback = callback

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        sub = Subscription(
            mode="MERGE", items=IDENTIFIERS, fields=["TimeStamp", "Value"]
        )
        # sub.setDataAdapter("QUOTE_ADAPTER")
        sub.setRequestedSnapshot("yes")
        sub.addListener(
            SubListener(callback=self.callback, loop=loop, subscribed_items=SUBS)
        )

        client = LightstreamerClient("http://push.lightstreamer.com", "ISSLIVE")
        client.connectionOptions.setSlowingEnabled(False)
        client.subscribe(sub)
        client.connect()

        print("Lightstreamer connected.")
