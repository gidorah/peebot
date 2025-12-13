import asyncio
from typing import Any

from django.core.management.base import BaseCommand

from apps.telemetry_ingestion.services.lightstreamer_client import (
    LightstreamerClientService,
)


class Command(BaseCommand):
    help = "Starts the ISS Lightstreamer ingestion client"

    def handle(self, *args: Any, **options: Any) -> None:
        asyncio.run(self.run_async())

    async def run_async(self) -> None:
        async def on_data_received(incoming_data: dict[str, dict]) -> None:
            print("Message received! Pipeline will process the data")
            print(f"timestamp: {incoming_data}")

        client = LightstreamerClientService(callback=on_data_received)
        await client.connect()
        await asyncio.Event().wait()
        print("event loop exited")
