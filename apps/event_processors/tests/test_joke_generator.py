"""Tests for the JokeGenerator service.

Verifies prompt construction, retry logic, error handling,
and integration with the OpenAI SDK.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.event_processors.models import DetectedEvent
from apps.event_processors.services.joke_generator import (
    JokeGenerator,
    JokeGeneratorError,
)


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
