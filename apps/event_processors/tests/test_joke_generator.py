"""Tests for the JokeGenerator service.

Verifies prompt construction, retry logic, error handling,
and integration with the OpenAI SDK.
"""

from __future__ import annotations

import asyncio
import gc
import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.event_processors.models import DetectedEvent
from apps.event_processors.services.joke_generator import (
    JokeGenerator,
    JokeGeneratorError,
)


class _OpenAIHandler(BaseHTTPRequestHandler):
    """Serve one OpenAI-compatible response over a reusable HTTP connection."""

    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(content_length)
        body = json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Test joke",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: Any) -> None:
        pass


@pytest.mark.asyncio
async def test_async_context_closes_openai_client() -> None:
    """Leaving the generator context closes its OpenAI client."""
    client = AsyncMock()

    with (
        patch(
            "apps.event_processors.services.joke_generator.settings"
        ) as mock_settings,
        patch(
            "apps.event_processors.services.joke_generator.AsyncOpenAI",
            return_value=client,
        ),
    ):
        mock_settings.OPENROUTER_API_KEY = "test_key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "deepseek/deepseek-chat"
        mock_settings.JOKE_GENERATOR_MAX_RETRIES = 3
        mock_settings.JOKE_GENERATOR_BASE_DELAY = 1.0

        generator = JokeGenerator()
        async with generator as entered:
            assert entered is generator

    client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_context_closes_client_and_propagates_cancellation() -> None:
    """Cancellation still closes the client and remains observable to callers."""
    client = AsyncMock()

    with (
        patch(
            "apps.event_processors.services.joke_generator.settings"
        ) as mock_settings,
        patch(
            "apps.event_processors.services.joke_generator.AsyncOpenAI",
            return_value=client,
        ),
    ):
        mock_settings.OPENROUTER_API_KEY = "test_key"
        generator = JokeGenerator()

        with pytest.raises(asyncio.CancelledError):
            async with generator:
                raise asyncio.CancelledError

    client.close.assert_awaited_once_with()


def test_async_context_prevents_cross_loop_client_cleanup_error() -> None:
    """A used client is closed before a later task creates a fresh event loop."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    retained_generators: list[JokeGenerator] = []
    loop_errors: list[dict[str, Any]] = []
    event = MagicMock(spec=DetectedEvent)
    event.id = "test-uuid"
    event.event_type = "urination"
    event.metadata = {"duration_seconds": 30, "delta": "3.0"}
    event.confidence = Decimal("0.80")

    async def use_client_on_first_loop() -> None:
        generator = JokeGenerator()
        async with generator:
            assert await generator.generate(event) == "Test joke"
        retained_generators.append(generator)

    async def collect_client_on_second_loop() -> None:
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, context: loop_errors.append(context)
        )
        retained_generators.clear()
        gc.collect()
        await asyncio.sleep(0.05)

    try:
        with patch(
            "apps.event_processors.services.joke_generator.settings"
        ) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.OPENROUTER_BASE_URL = (
                f"http://127.0.0.1:{server.server_port}/v1"
            )
            mock_settings.OPENROUTER_MODEL = "test-model"
            mock_settings.JOKE_GENERATOR_MAX_RETRIES = 1
            mock_settings.JOKE_GENERATOR_BASE_DELAY = 0

            asyncio.run(use_client_on_first_loop())
            asyncio.run(collect_client_on_second_loop())
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1)

    assert not loop_errors


class TestJokeGeneratorInitialization:
    """Tests for JokeGenerator initialization and configuration."""

    @patch("apps.event_processors.services.joke_generator.settings")
    def test_init_with_valid_settings(self, mock_settings: MagicMock) -> None:
        """JokeGenerator initializes with valid API key."""
        mock_settings.OPENROUTER_API_KEY = "test_api_key"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "deepseek/deepseek-chat"
        mock_settings.JOKE_GENERATOR_MAX_RETRIES = 3
        mock_settings.JOKE_GENERATOR_BASE_DELAY = 1.0

        generator = JokeGenerator()

        assert generator.client is not None
        assert generator.model == "deepseek/deepseek-chat"  # Default
        assert generator.max_retries == 3  # Default
        assert generator.base_delay == 1.0  # Default

    @patch("apps.event_processors.services.joke_generator.settings")
    def test_init_with_custom_settings(self, mock_settings: MagicMock) -> None:
        """JokeGenerator uses custom settings when provided."""
        mock_settings.OPENROUTER_API_KEY = "test_api_key"
        mock_settings.OPENROUTER_BASE_URL = "https://custom.openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "custom/model"
        mock_settings.JOKE_GENERATOR_MAX_RETRIES = 5
        mock_settings.JOKE_GENERATOR_BASE_DELAY = 2.0

        generator = JokeGenerator()

        assert generator.model == "custom/model"
        assert generator.max_retries == 5
        assert generator.base_delay == 2.0

    @patch("apps.event_processors.services.joke_generator.settings")
    def test_init_without_api_key_raises_error(self, mock_settings: MagicMock) -> None:
        """JokeGenerator raises error when API key not configured."""
        mock_settings.OPENROUTER_API_KEY = None

        with pytest.raises(JokeGeneratorError) as exc_info:
            JokeGenerator()

        assert "OPENROUTER_API_KEY" in str(exc_info.value)


class TestJokeGeneratorPrompt:
    """Tests for prompt construction."""

    def _create_mock_generator(self) -> JokeGenerator:
        """Create JokeGenerator with mocked settings."""
        with patch(
            "apps.event_processors.services.joke_generator.settings"
        ) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
            mock_settings.OPENROUTER_MODEL = "deepseek/deepseek-chat"
            mock_settings.JOKE_GENERATOR_MAX_RETRIES = 3
            mock_settings.JOKE_GENERATOR_BASE_DELAY = 1.0
            return JokeGenerator()

    def test_build_prompt_includes_event_details(self) -> None:
        """Prompt includes event metadata."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.metadata = {
            "duration_seconds": 45,
            "delta": "5.2",
            "tank_level_start": "23.4",
            "tank_level_end": "28.6",
        }
        event.confidence = Decimal("0.85")

        prompt = mock_generator._build_prompt(event)

        assert "45 seconds" in prompt
        assert "5.2%" in prompt
        assert "23.4%" in prompt
        assert "28.6%" in prompt
        assert "85%" in prompt or "0.85" in prompt or "85" in prompt
        assert "ISS UPA" in prompt
        assert "dry, scientifically accurate" in prompt

    def test_build_prompt_formats_long_duration(self) -> None:
        """Prompt formats duration > 60s as minutes."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.metadata = {"duration_seconds": 90, "delta": "5.0"}
        event.confidence = Decimal("0.75")

        prompt = mock_generator._build_prompt(event)

        assert "1.5 minutes" in prompt


@pytest.mark.asyncio
class TestJokeGeneratorGenerate:
    """Tests for the generate method."""

    def _create_mock_generator(self) -> JokeGenerator:
        """Create JokeGenerator with mocked settings and client."""
        with patch(
            "apps.event_processors.services.joke_generator.settings"
        ) as mock_settings:
            mock_settings.OPENROUTER_API_KEY = "test_key"
            mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
            mock_settings.OPENROUTER_MODEL = "deepseek/deepseek-chat"
            mock_settings.JOKE_GENERATOR_MAX_RETRIES = 2  # Reduce for tests
            mock_settings.JOKE_GENERATOR_BASE_DELAY = 0.1  # Fast for tests
            generator = JokeGenerator()
            generator.client = AsyncMock()
            return generator

    @pytest.mark.asyncio
    async def test_generate_success(self) -> None:
        """Generate returns text on successful API call."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.id = "test-uuid"
        event.event_type = "urination"
        event.metadata = {"duration_seconds": 45, "delta": "5.0"}
        event.confidence = Decimal("0.85")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "  ISS crew hydration update!  "
        mock_generator.client.chat.completions.create.return_value = mock_response

        result = await mock_generator.generate(event)

        assert result == "ISS crew hydration update!"
        assert mock_generator.client.chat.completions.create.called

    @pytest.mark.asyncio
    async def test_generate_empty_response_returns_none(self) -> None:
        """Generate returns None for empty API response."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.id = "test-uuid"
        event.event_type = "urination"
        event.metadata = {}
        event.confidence = Decimal("0.50")

        mock_response = MagicMock()
        mock_response.choices = []
        mock_generator.client.chat.completions.create.return_value = mock_response

        result = await mock_generator.generate(event)

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_retries_on_failure(self) -> None:
        """Generate retries on API failure with exponential backoff."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.id = "test-uuid"
        event.event_type = "urination"
        event.metadata = {}
        event.confidence = Decimal("0.50")

        # First call fails, second succeeds
        mock_generator.client.chat.completions.create.side_effect = [
            Exception("API timeout"),
            MagicMock(
                choices=[MagicMock(message=MagicMock(content="Success after retry"))]
            ),
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await mock_generator.generate(event)

        assert result == "Success after retry"
        assert mock_generator.client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_returns_none_after_all_retries_fail(self) -> None:
        """Generate returns None after all retry attempts fail."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.id = "test-uuid"
        event.event_type = "urination"
        event.metadata = {}
        event.confidence = Decimal("0.50")

        mock_generator.client.chat.completions.create.side_effect = Exception(
            "Persistent API error"
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await mock_generator.generate(event)

        assert result is None
        assert (
            mock_generator.client.chat.completions.create.call_count == 2
        )  # max_retries

    @pytest.mark.asyncio
    async def test_generate_uses_correct_model_and_messages(self) -> None:
        """Generate uses correct model and message structure."""
        mock_generator = self._create_mock_generator()
        event = MagicMock(spec=DetectedEvent)
        event.id = "test-uuid"
        event.event_type = "urination"
        event.metadata = {"duration_seconds": 30, "delta": "3.0"}
        event.confidence = Decimal("0.80")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test joke"
        mock_generator.client.chat.completions.create.return_value = mock_response

        await mock_generator.generate(event)

        call_args = mock_generator.client.chat.completions.create.call_args
        assert call_args[1]["model"] == "deepseek/deepseek-chat"
        assert call_args[1]["max_tokens"] == 100
        assert call_args[1]["temperature"] == 0.7
        assert len(call_args[1]["messages"]) == 2
        assert call_args[1]["messages"][0]["role"] == "system"
        assert call_args[1]["messages"][1]["role"] == "user"
