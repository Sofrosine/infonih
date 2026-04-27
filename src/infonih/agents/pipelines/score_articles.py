"""Pipeline that fetches a batch of unscored articles and scores them with Claude.

Run on a schedule (every `score_interval_minutes` per Settings) by the worker.
Operates on adapters via the Protocol shapes — usable from tests with fakes.
"""

from loguru import logger
from pydantic import BaseModel, ConfigDict

from infonih.adapters.anthropic_adapter import AnthropicAdapter, AnthropicError
from infonih.agents.prompts.prompts import SCORE_ARTICLE
from infonih.agents.schemas.article_score_schema import ArticleScoreSchema
from infonih.config import settings
from infonih.domain.repositories.article_repository import ArticleRepository
from infonih.domain.repositories.user_settings_repository import (
    UserSettingsRepository,
)


class ScoreArticlesResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    scored: int = 0
    failed: int = 0
    skipped: bool = False
    skip_reason: str | None = None


class ScoreArticlesPipeline:
    """Fetch unscored articles → score each → mark scored or score_failed."""

    def __init__(
        self,
        *,
        anthropic: AnthropicAdapter,
        article_repo: ArticleRepository,
        user_settings_repo: UserSettingsRepository,
    ) -> None:
        self._anthropic = anthropic
        self._article_repo = article_repo
        self._user_settings_repo = user_settings_repo

    async def run(self, *, batch_size: int | None = None) -> ScoreArticlesResult:
        user_settings = await self._user_settings_repo.get()
        if user_settings is None:
            logger.info("no user settings; skipping scoring batch")
            return ScoreArticlesResult(skipped=True, skip_reason="no_user_settings")

        articles = await self._article_repo.list_unscored(
            limit=batch_size or settings.score_batch_size,
        )
        if not articles:
            return ScoreArticlesResult()

        scored = failed = 0
        for article in articles:
            try:
                result = await self._anthropic.complete_structured(
                    schema=ArticleScoreSchema,
                    system=SCORE_ARTICLE.format(
                        interests=user_settings.interests_text,
                        source_name=", ".join(article.sources) or "unknown",
                        source_category="unknown",  # category is per-source, not per-article
                        title=article.title,
                        content=(article.raw_content or "")[:4000],
                        recent_reactions="(no reactions yet)",
                    ),
                    user="Score this article and return the structured response.",
                    model=settings.score_model,
                )
                await self._article_repo.mark_scored(
                    article.id,
                    score=result.score,
                    reasoning=result.reasoning,
                    interests_version=user_settings.interests_version,
                    low_content_confidence=result.low_content_confidence,
                )
                scored += 1
            except AnthropicError as exc:
                logger.warning(
                    "score failed for article {id}: {err}", id=article.id, err=exc
                )
                await self._article_repo.mark_score_failed(article.id, reason=str(exc))
                failed += 1

        logger.info("scored batch: scored={s} failed={f}", s=scored, f=failed)
        return ScoreArticlesResult(scored=scored, failed=failed)
