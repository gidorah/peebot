import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.telemetry_ingestion.services.lightstreamer_client import (
    LightstreamerClientService,
    SubListener,
)


class TestLightstreamerClientService:
    @patch("apps.telemetry_ingestion.services.lightstreamer_client.LightstreamerClient")
    @patch("apps.telemetry_ingestion.services.lightstreamer_client.Subscription")
    @pytest.mark.asyncio
    async def test_connect(self, mock_subscription, mock_lightstreamer_client):
        """
        Verify that connecting initializes the client and subscription correctly.
        """
        # Arrange
        mock_callback = AsyncMock()
        service = LightstreamerClientService(callback=mock_callback)
        mock_client_instance = mock_lightstreamer_client.return_value

        # Act
        await service.connect()

        # Assert
        # 1. Verify Client Initialization
        mock_lightstreamer_client.assert_called_once_with(
            "http://push.lightstreamer.com", "ISSLIVE"
        )
        mock_client_instance.connectionOptions.setSlowingEnabled.assert_called_once_with(
            False
        )
        mock_client_instance.connect.assert_called_once()

        # 2. Verify Subscription Configuration
        mock_subscription.assert_called_once()
        call_kwargs = mock_subscription.call_args[1]
        assert call_kwargs["mode"] == "MERGE"
        assert "TimeStamp" in call_kwargs["fields"]
        assert "Value" in call_kwargs["fields"]

        # 3. Verify Subscription Registration
        mock_sub_instance = mock_subscription.return_value
        mock_sub_instance.setRequestedSnapshot.assert_called_once_with("yes")
        # Ensure a listener was added
        assert mock_sub_instance.addListener.called
        # Ensure subscribe was called with the subscription object
        mock_client_instance.subscribe.assert_called_once_with(mock_sub_instance)

    @pytest.mark.asyncio
    async def test_listener_callback_execution(self):
        """
        Verify that the SubListener correctly bridges the synchronous onItemUpdate
        to the asynchronous callback.
        """
        # Arrange
        mock_callback = AsyncMock()
        loop = asyncio.get_running_loop()
        subscribed_items = ["NODE3000004"]

        listener = SubListener(
            callback=mock_callback, loop=loop, subscribed_items=subscribed_items
        )

        # Mock an ItemUpdate object from Lightstreamer
        mock_update = MagicMock()
        mock_update.getItemName.return_value = "NODE3000004"
        mock_update.getChangedFields.return_value = {"Value": "10.5"}

        # Act
        # Simulate Lightstreamer calling the listener (synchronously)
        listener.onItemUpdate(mock_update)

        # Assert
        # Since the listener schedules the coro on the loop, we yield control briefly
        # to allow the event loop to execute the scheduled callback.
        await asyncio.sleep(0)

        expected_data = {"NODE3000004": {"Value": "10.5"}}
        mock_callback.assert_called_once_with(expected_data)

    @pytest.mark.asyncio
    async def test_listener_ignores_unsubscribed_items(self):
        """
        Verify that the listener ignores updates for items not in our list.
        """
        # Arrange
        mock_callback = AsyncMock()
        loop = asyncio.get_running_loop()
        listener = SubListener(
            callback=mock_callback, loop=loop, subscribed_items=["NODE3000004"]
        )

        mock_update = MagicMock()
        mock_update.getItemName.return_value = "UNKNOWN_ITEM"

        # Act
        listener.onItemUpdate(mock_update)
        await asyncio.sleep(0)

        # Assert
        mock_callback.assert_not_called()
