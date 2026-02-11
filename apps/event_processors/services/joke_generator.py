"""JokeGenerator service - LLM integration for humorous text generation.

This module provides the JokeGenerator class which uses the OpenAI SDK to
generate humorous, scientific text about detected ISS urination events.
It connects to OpenRouter to access the DeepSeek model.

The generated content follows a "dry, scientific, slightly absurd" tone
as specified in the requirements, making light of the serious business
of astronaut bodily functions.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from django.conf import settings
from openai import AsyncOpenAI

if TYPE_CHECKING:
    from apps.event_processors.models import DetectedEvent

logger = structlog.get_logger(__name__)


class JokeGeneratorError(Exception):
    """Base exception for JokeGenerator errors."""

    pass


class JokeGenerator:
    """Generates humorous text about detected events using LLM.

    Uses OpenAI SDK configured for OpenRouter endpoint with DeepSeek model.
    Implements retry logic with exponential backoff for resilience.

    Attributes:
        client: AsyncOpenAI client configured for OpenRouter
        model: Model identifier (default: deepseek/deepseek-chat)
        max_retries: Maximum retry attempts (default: 3)
    """

    DEFAULT_MODEL = "deepseek/deepseek-chat"
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BASE_DELAY = 1.0  # seconds

    def __init__(self) -> None:
        """Initialize the JokeGenerator with OpenAI client.

        Raises:
            JokeGeneratorError: If OPENROUTER_API_KEY is not configured
        """
        api_key = getattr(settings, "OPENROUTER_API_KEY", None)
        if not api_key:
            raise JokeGeneratorError("OPENROUTER_API_KEY not configured in settings")

        base_url = getattr(
            settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = getattr(settings, "OPENROUTER_MODEL", self.DEFAULT_MODEL)
        self.max_retries = getattr(
            settings, "JOKE_GENERATOR_MAX_RETRIES", self.DEFAULT_MAX_RETRIES
        )
        self.base_delay = getattr(
            settings, "JOKE_GENERATOR_BASE_DELAY", self.DEFAULT_BASE_DELAY
        )

    async def generate(self, event: DetectedEvent) -> str | None:
        """Generate humorous text about a detected event.

        Constructs a prompt with event details and sends it to the LLM
        for text generation. Implements retry logic with exponential backoff.

        Args:
            event: The DetectedEvent to generate content about

        Returns:
            Generated text string, or None if generation failed after retries
        """
        prompt = self._build_prompt(event)

        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a dry, scientific commentator with a "
                                "slightly absurd sense of humor. You write about "
                                "ISS operations with deadpan wit. Keep responses "
                                "under 300 characters (social media limit). Be factual "
                                "but amusing."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    max_tokens=100,
                    temperature=0.7,
                )

                if response.choices and response.choices[0].message.content:
                    generated_text = response.choices[0].message.content.strip()
                    logger.info(
                        "joke_generated",
                        event_id=str(event.id),
                        event_type=event.event_type,
                        model=self.model,
                        attempt=attempt + 1,
                        text_length=len(generated_text),
                    )
                    return generated_text

                logger.warning(
                    "empty_response_from_llm",
                    event_id=str(event.id),
                    attempt=attempt + 1,
                )
                return None

            except Exception as e:
                logger.warning(
                    "joke_generation_attempt_failed",
                    event_id=str(event.id),
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                if attempt < self.max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = self.base_delay * (2**attempt)
                    logger.info(
                        "retrying_after_delay",
                        delay_seconds=delay,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "joke_generation_failed_all_retries",
                        event_id=str(event.id),
                        error=str(e),
                        error_type=type(e).__name__,
                    )

        return None

    def _build_prompt(self, event: DetectedEvent) -> str:
        """Build a prompt for the LLM based on event details.

        Args:
            event: The DetectedEvent to build prompt for

        Returns:
            Formatted prompt string
        """
        metadata = event.metadata or {}

        # Extract relevant information from metadata
        duration = metadata.get("duration_seconds", 0)
        delta = metadata.get("delta", "unknown")
        tank_start = metadata.get("tank_level_start", "unknown")
        tank_end = metadata.get("tank_level_end", "unknown")
        confidence_sentence = ""
        if event.confidence is not None:
            confidence_sentence = (
                f"Detection confidence: {float(event.confidence):.0%}. "
            )

        # Format duration nicely
        if duration < 60:
            duration_str = f"{int(duration)} seconds"
        else:
            duration_str = f"{duration / 60:.1f} minutes"

        prompt = (
            f"The ISS UPA (Urine Processing Assembly) tank level just increased "
            f"by {delta}% over {duration_str}. "
            f"Initial level: {tank_start}%, final level: {tank_end}%. "
            f"{confidence_sentence}"
            f"Write a dry, scientifically accurate but slightly absurd post "
            f"about this astronaut bodily function event. "
            f"Make it sound like a mission control announcement with understated "
            f"wit. Keep it under 300 characters."
        )

        return prompt
