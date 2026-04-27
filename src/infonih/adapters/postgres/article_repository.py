from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text

from infonih.adapters.postgres.models import ArticleModel
from infonih.adapters.postgres.postgres_adapter import PostgresAdapter
from infonih.domain.article import Article, ArticleStatus
from infonih.domain.repositories.article_repository import IngestOutcome, IngestResult

# Single-statement, race-safe upsert with three-way outcome detection.
#
# How it works:
#   1. CTE `old` snapshots the existing row's `sources` array BEFORE the
#      insert (CTEs in a single statement see a consistent pre-statement
#      snapshot).
#   2. CTE `ins` performs INSERT ... ON CONFLICT DO UPDATE, deduplicating
#      the sources union via DISTINCT unnest.
#   3. The outer SELECT compares: was the row inserted (xmax = 0)? Or did
#      `source_name` already appear in the pre-update snapshot (DUPLICATE)?
#      Otherwise the source must have been newly appended.
#
# `xmax = 0` is the standard Postgres trick for distinguishing inserts from
# updates inside an ON CONFLICT. It's reliable for our single-writer ingest.
_INSERT_OR_APPEND_SQL = text(
    """
    WITH old AS (
        SELECT sources
        FROM articles
        WHERE user_id IS NOT DISTINCT FROM :user_id
          AND url_normalized = :url_normalized
    ),
    ins AS (
        INSERT INTO articles (
            user_id, url_normalized, url_original, title, raw_content,
            published_at, sources, is_backfill
        )
        VALUES (
            :user_id, :url_normalized, :url_original, :title, :raw_content,
            :published_at, ARRAY[:source_name]::text[], :is_backfill
        )
        ON CONFLICT ON CONSTRAINT uq_articles_user_url DO UPDATE
        SET sources = ARRAY(
            SELECT DISTINCT s
            FROM unnest(articles.sources || EXCLUDED.sources) AS s
        )
        RETURNING id, (xmax = 0) AS was_inserted
    )
    SELECT
        ins.id,
        CASE
            WHEN ins.was_inserted THEN 'inserted'
            WHEN (SELECT sources FROM old) @> ARRAY[:source_name]::text[]
                THEN 'duplicate'
            ELSE 'source_appended'
        END AS outcome
    FROM ins;
    """
)


class PostgresArticleRepository:
    """Postgres implementation of `ArticleRepository`."""

    def __init__(self, adapter: PostgresAdapter) -> None:
        self._adapter = adapter

    async def insert_or_append_source(
        self,
        *,
        url_normalized: str,
        url_original: str,
        title: str,
        published_at: datetime,
        source_name: str,
        raw_content: str | None = None,
        is_backfill: bool = False,
        user_id: UUID | None = None,
    ) -> IngestResult:
        params = {
            "user_id": user_id,
            "url_normalized": url_normalized,
            "url_original": url_original,
            "title": title,
            "raw_content": raw_content,
            "published_at": published_at,
            "source_name": source_name,
            "is_backfill": is_backfill,
        }
        async with self._adapter.session() as session:
            result = await session.execute(_INSERT_OR_APPEND_SQL, params)
            row = result.one()
            return IngestResult(article_id=row.id, outcome=IngestOutcome(row.outcome))

    async def find_by_url(
        self, url_normalized: str, *, user_id: UUID | None = None
    ) -> Article | None:
        stmt = select(ArticleModel).where(
            ArticleModel.user_id.is_(user_id),
            ArticleModel.url_normalized == url_normalized,
        )
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return _to_domain(model) if model is not None else None

    async def list_unscored(
        self, *, limit: int = 100, user_id: UUID | None = None
    ) -> list[Article]:
        stmt = (
            select(ArticleModel)
            .where(
                ArticleModel.user_id.is_(user_id),
                ArticleModel.status == ArticleStatus.UNSCORED,
            )
            .order_by(ArticleModel.published_at.desc())
            .limit(limit)
        )
        async with self._adapter.session() as session:
            result = await session.execute(stmt)
            return [_to_domain(m) for m in result.scalars()]


def _to_domain(model: ArticleModel) -> Article:
    return Article(
        id=model.id,
        user_id=model.user_id,
        url_normalized=model.url_normalized,
        url_original=model.url_original,
        title=model.title,
        raw_content=model.raw_content,
        published_at=model.published_at,
        sources=list(model.sources),
        status=model.status,
        score=model.score,
        score_reasoning=model.score_reasoning,
        low_content_confidence=model.low_content_confidence,
        scored_at=model.scored_at,
        scored_with_interest_version=model.scored_with_interest_version,
        score_failure_reason=model.score_failure_reason,
        is_backfill=model.is_backfill,
        sent_in_digest_at=model.sent_in_digest_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
