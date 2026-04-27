"""Anthropic SDK wrapper.

Thin async singleton over `anthropic.AsyncAnthropic`. Exposes one method:
`complete_structured`, which uses `messages.parse(output_format=...)` to
constrain the response to a Pydantic schema and returns a validated instance.

Why this shape: every LLM call in infonih (article scoring, digest summary,
future flows) wants structured output. Centralising the parse + retry +
error-translation logic here keeps chains stupid.
"""

from typing import TypeVar

from anthropic import AsyncAnthropic
from loguru import logger
from pydantic import BaseModel

from infonih.config import settings

T = TypeVar("T", bound=BaseModel)


class AnthropicError(Exception):
    """Raised when an LLM call fails after the SDK's built-in retries."""


class AnthropicAdapter:
    """Singleton wrapper around the async Anthropic SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key if api_key is not None else settings.anthropic_api_key.get_secret_value()
        # Empty key is acceptable at import time (tests don't need it); the
        # SDK will raise if you actually try to call without one.
        self._client = AsyncAnthropic(api_key=key or "placeholder")

    async def complete_structured(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> T:
        """Call Claude with a Pydantic output schema; return a validated instance.

        Raises:
            AnthropicError: any SDK exception, with the original wrapped.
        """
        try:
            response = await self._client.messages.parse(
                model=model or settings.score_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except Exception as exc:
            logger.warning("anthropic call failed: {err}", err=exc)
            raise AnthropicError(str(exc)) from exc
        return response.parsed_output  # type: ignore[no-any-return]

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Plain text completion (no structured output). Used for digest summaries."""
        try:
            response = await self._client.messages.create(
                model=model or settings.summarize_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            logger.warning("anthropic call failed: {err}", err=exc)
            raise AnthropicError(str(exc)) from exc
        for block in response.content:
            if block.type == "text":
                return block.text
        raise AnthropicError("no text block in response")


anthropic_adapter = AnthropicAdapter()
