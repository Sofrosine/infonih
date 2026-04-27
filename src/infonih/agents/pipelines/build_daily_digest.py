"""Daily digest pipeline.

Per FLOWS.md §204: query candidates → cap globally (per-category caps and
embedding-based topic dedup deferred to v2 per PRODUCT.md open questions)
→ summarize each via Claude → format → send via Telegram → mark sent.

This is the user-facing endpoint of the whole product. Everything before
this step exists to feed it.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from pydantic import BaseModel, ConfigDict

from infonih.adapters.anthropic_adapter import AnthropicAdapter, AnthropicError
from infonih.adapters.telegram_adapter import TelegramAdapter
from infonih.agents.prompts.prompts import SUMMARIZE_FOR_DIGEST
from infonih.agents.utils.digest.format_telegram_message import format_digest
from infonih.config import settings
from infonih.domain.article import Article
from infonih.domain.repositories.article_repository import ArticleRepository


class DigestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_count: int
    sent: bool
    skip_reason: str | None = None


class BuildDailyDigestPipeline:
    """Assemble and deliver the daily digest."""

    def __init__(
        self,
        *,
        anthropic: AnthropicAdapter,
        article_repo: ArticleRepository,
        telegram: TelegramAdapter,
    ) -> None:
        self._anthropic = anthropic
        self._article_repo = article_repo
        self._telegram = telegram

    async def run(self) -> DigestResult:
        now = datetime.now(UTC)
        candidates = await self._article_repo.list_digest_candidates(
            score_threshold=settings.score_threshold,
            published_after=now - timedelta(hours=settings.digest_window_hours),
        )

        # Global cap; per-category and topic dedup deferred to v2.
        selected = candidates[: settings.digest_max_items]

        if not selected:
            text = format_digest(items=[], digest_date=now.date())
            await self._telegram.send(text)
            logger.info("digest sent: low-signal day")
            return DigestResult(item_count=0, sent=True, skip_reason="low_signal")

        summaries = await asyncio.gather(
            *(self._summarize(a) for a in selected), return_exceptions=False
        )
        items: list[tuple[Article, str]] = list(zip(selected, summaries, strict=True))

        text = format_digest(items=items, digest_date=now.date())
        await self._telegram.send(text)
        await self._article_repo.mark_sent_in_digest(
            [a.id for a in selected], sent_at=now
        )
        logger.info("digest sent: {n} items", n=len(selected))
        return DigestResult(item_count=len(selected), sent=True)

    async def _summarize(self, article: Article) -> str:
        try:
            return await self._anthropic.complete_text(
                system=SUMMARIZE_FOR_DIGEST.format(
                    title=article.title,
                    source_name=", ".join(article.sources) or "unknown",
                    source_category="unknown",
                    content=(article.raw_content or "")[:4000],
                ),
                user="Write the digest summary now.",
                model=settings.summarize_model,
                max_tokens=400,
            )
        except AnthropicError as exc:
            logger.warning("summary failed for {id}: {err}", id=article.id, err=exc)
            return article.title  # fall back to title; better than dropping the item


def _digest_today(now: datetime) -> date:
    return now.date()
