"""Tests for the Lightstreamer SDK wrappers (sync→async bridge, listeners, service)."""

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
    async def test_connect(
        self, mock_subscription: MagicMock, mock_lightstreamer_client: MagicMock
    ) -> None:
        """Verify that connecting initializes the client and subscription correctly."""
        # Arrange
        mock_callback = AsyncMock()
        item_names = ["NODE3000005", "AIRLOCK000001"]
        service = LightstreamerClientService(
            item_names=item_names, callback=mock_callback
        )
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
        assert call_kwargs["items"] == item_names
        assert "TimeStamp" in call_kwargs["fields"]
        assert "Value" in call_kwargs["fields"]
        assert "Status.Class" in call_kwargs["fields"]
        assert "Status.Indicator" in call_kwargs["fields"]
        assert "Status.Color" in call_kwargs["fields"]

        # 3. Verify Subscription Registration
        mock_sub_instance = mock_subscription.return_value
        mock_sub_instance.setRequestedSnapshot.assert_called_once_with("yes")
        # Ensure a listener was added
        assert mock_sub_instance.addListener.called
        # Ensure subscribe was called with the subscription object
        mock_client_instance.subscribe.assert_called_once_with(mock_sub_instance)

    @pytest.mark.asyncio
    async def test_listener_callback_execution(self) -> None:
        """Verify that the SubListener bridges onItemUpdate to the async callback.

        The SubListener must correctly forward the synchronous onItemUpdate
        hook from the Lightstreamer SDK into the asynchronous coroutine callback.
        """
        # Arrange
        mock_callback = AsyncMock()
        loop = asyncio.get_running_loop()

        listener = SubListener(callback=mock_callback, loop=loop)

        # Mock an ItemUpdate object from Lightstreamer
        mock_update = MagicMock()
        mock_update.getItemName.return_value = "NODE3000005"
        mock_update.getChangedFields.return_value = {"Value": "10.5"}

        # Act
        # Simulate Lightstreamer calling the listener (synchronously)
        listener.onItemUpdate(mock_update)

        # Assert
        # Since the listener schedules the coro on the loop, we yield control briefly
        # to allow the event loop to execute the scheduled callback.
        await asyncio.sleep(0)

        expected_data = {"NODE3000005": {"Value": "10.5"}}
        mock_callback.assert_called_once_with(expected_data)
