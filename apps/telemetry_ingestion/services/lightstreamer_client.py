from typing import Any
import asyncio

from lightstreamer.client import LightstreamerClient, Subscription, SubscriptionListener


class SubListener(SubscriptionListener):  # type: ignore[misc]
    def __init__(self, callback: Any, loop: asyncio.AbstractEventLoop) -> None:
        self.callback = callback
        self.loop = loop

    def onItemUpdate(self, update: Any) -> None:
        msg = (
            "UPDATE "
            + update.getValue("stock_name")
            + " "
            + update.getValue("last_price")
        )
        print(msg)
        asyncio.run_coroutine_threadsafe(self.callback(msg), self.loop)


class LightstreamerClientService:
    def __init__(self, callback: Any) -> None:
        self.callback = callback

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        sub = Subscription(
            "MERGE", ["item1", "item2", "item3"], ["stock_name", "last_price"]
        )
        sub.setDataAdapter("QUOTE_ADAPTER")
        sub.setRequestedSnapshot("yes")
        sub.addListener(SubListener(callback=self.callback, loop=loop))

        client = LightstreamerClient("http://push.lightstreamer.com", "DEMO")
        client.subscribe(sub)
        client.connect()

        print("Lightstreamer connected.")
