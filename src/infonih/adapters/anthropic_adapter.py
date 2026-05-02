"""Anthropic SDK wrapper.

Thin async singleton over `anthropic.AsyncAnthropic`. Two methods:

* `complete_structured` — uses `messages.parse(output_format=...)` to
  constrain the response to a Pydantic schema and returns a validated
  instance.
* `complete_text` — plain text completion via `messages.create`. Used by
  the digest summarizer.

Both methods record a cost row on every successful call. Cost-recording
failure is logged but never bubbles up — an audit-log write must not
break a working LLM call.
"""

from typing import TypeVar
from uuid import UUID

from anthropic import AsyncAnthropic
from loguru import logger
from pydantic import BaseModel

from infonih.agents.utils.llm.pricing import cost_usd
from infonih.config import settings
from infonih.domain.repositories.cost_repository import CostRepository

T = TypeVar("T", bound=BaseModel)


class AnthropicError(Exception):
    """Raised when an LLM call fails after the SDK's built-in retries."""


class AnthropicAdapter:
    """Singleton wrapper around the async Anthropic SDK."""

    def __init__(self, *, cost_repo: CostRepository, api_key: str | None = None) -> None:
        key = api_key if api_key is not None else settings.anthropic_api_key.get_secret_value()
        # Empty key is acceptable at import time (tests don't need it); the
        # SDK will raise if you actually try to call without one.
        self._client = AsyncAnthropic(api_key=key or "placeholder")
        self._cost_repo = cost_repo

    async def complete_structured(
        self,
        *,
        schema: type[T],
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        flow: str = "unknown",
        article_id: UUID | None = None,
    ) -> T:
        """Call Claude with a Pydantic output schema; return a validated instance.

        Raises:
            AnthropicError: any SDK exception, with the original wrapped.
        """
        actual_model = model or settings.score_model
        try:
            response = await self._client.messages.parse(
                model=actual_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except Exception as exc:
            logger.warning("anthropic call failed: {err}", err=exc)
            raise AnthropicError(str(exc)) from exc

        await self._record_cost(
            response=response, model=actual_model, flow=flow, article_id=article_id
        )
        return response.parsed_output  # type: ignore[no-any-return]

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 1024,
        flow: str = "unknown",
        article_id: UUID | None = None,
    ) -> str:
        """Plain text completion (no structured output). Used for digest summaries."""
        actual_model = model or settings.summarize_model
        try:
            response = await self._client.messages.create(
                model=actual_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            logger.warning("anthropic call failed: {err}", err=exc)
            raise AnthropicError(str(exc)) from exc

        await self._record_cost(
            response=response, model=actual_model, flow=flow, article_id=article_id
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        raise AnthropicError("no text block in response")

    async def _record_cost(
        self,
        *,
        response: object,
        model: str,
        flow: str,
        article_id: UUID | None,
    ) -> None:
        """Best-effort write to the cost_events table. Swallows all errors —
        the LLM call already succeeded; an audit-log failure must not
        propagate."""
        try:
            usage = response.usage  # type: ignore[attr-defined]
            input_tokens = int(usage.input_tokens)
            output_tokens = int(usage.output_tokens)
            cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            await self._cost_repo.record(
                flow=flow,
                provider="anthropic",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_input_tokens=cache_creation,
                cache_read_input_tokens=cache_read,
                cost_usd=cost_usd(
                    model=model, input_tokens=input_tokens, output_tokens=output_tokens
                ),
                article_id=article_id,
            )
        except Exception as exc:
            logger.warning(
                "cost recording failed (LLM call succeeded): {err}", err=exc
            )


# Module-level singleton — wired with the production cost repository.
# Tests construct their own AnthropicAdapter with a fake cost repo when
# they need to exercise the recording path.
from infonih.adapters.postgres import cost_repository  # noqa: E402

anthropic_adapter = AnthropicAdapter(cost_repo=cost_repository)
