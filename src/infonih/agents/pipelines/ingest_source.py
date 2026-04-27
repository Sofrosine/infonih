"""Deterministic pipeline that polls one source and ingests its articles.

Sequence per FLOWS.md §145:
    1. Fetch the feed via the configured fetcher (RSS today; HN/ArXiv later).
    2. Normalize each entry's URL.
    3. Insert (or append source on conflict) into the articles table.
    4. Stamp the source's `last_polled_at` and clear / increment failure counts.

First-poll backfill (FLOWS.md §72): on the very first poll for a source
(`last_polled_at IS NULL`), only ingest articles published within the last
`BACKFILL_WINDOW_DAYS` days, and mark them `is_backfill=True` so the digest
selector skips them. Subsequent polls ingest everything the feed returns
(URL dedup handles re-seen articles).

Failure policy: any `RssFetchError` is caught, the source is marked
`last_poll_status='failed'` with the error string, and the pipeline returns
an unsuccessful `IngestSourceResult`. Database failures during article
insert are NOT swallowed — they propagate so the scheduler retries.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, ConfigDict

from infonih.adapters.rss_adapter import RssAdapter, RssFetchError
from infonih.agents.utils.url.normalize_url import normalize_url
from infonih.domain.repositories.article_repository import (
    ArticleRepository,
    IngestOutcome,
)
from infonih.domain.repositories.source_repository import SourceRepository
from infonih.domain.source import PollStatus, Source

BACKFILL_WINDOW_DAYS = 7


class IngestSourceResult(BaseModel):
    """Outcome of one pipeline run, per FLOWS.md §160 logging requirements."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID
    source_name: str
    succeeded: bool
    inserted_count: int = 0
    appended_count: int = 0
    duplicate_count: int = 0
    skipped_for_backfill: int = 0
    error: str | None = None


class IngestSourcePipeline:
    """Coordinates one fetcher + the article and source repositories.

    Stateless. Safe to construct once at process startup and reuse for
    every source poll, or to construct per-call in scripts.
    """

    def __init__(
        self,
        *,
        rss: RssAdapter,
        article_repo: ArticleRepository,
        source_repo: SourceRepository,
        backfill_window_days: int = BACKFILL_WINDOW_DAYS,
    ) -> None:
        self._rss = rss
        self._article_repo = article_repo
        self._source_repo = source_repo
        self._backfill_window_days = backfill_window_days

    async def run(self, source: Source) -> IngestSourceResult:
        try:
            entries = await self._rss.fetch(str(source.url))
        except RssFetchError as exc:
            error = str(exc)
            logger.warning(
                "ingest failed for source '{name}': {err}",
                name=source.name,
                err=error,
            )
            await self._source_repo.mark_polled(
                source.id, status=PollStatus.FAILED, error=error
            )
            return IngestSourceResult(
                source_id=source.id,
                source_name=source.name,
                succeeded=False,
                error=error,
            )

        is_first_poll = source.last_polled_at is None
        backfill_cutoff = datetime.now(UTC) - timedelta(days=self._backfill_window_days)

        inserted = appended = duplicate = skipped = 0
        for entry in entries:
            if is_first_poll and entry.published_at < backfill_cutoff:
                skipped += 1
                continue

            normalized = normalize_url(str(entry.url))
            result = await self._article_repo.insert_or_append_source(
                url_normalized=normalized,
                url_original=str(entry.url),
                title=entry.title,
                published_at=entry.published_at,
                source_name=source.name,
                raw_content=entry.raw_content,
                is_backfill=is_first_poll,
                user_id=source.user_id,
            )
            if result.outcome is IngestOutcome.INSERTED:
                inserted += 1
            elif result.outcome is IngestOutcome.SOURCE_APPENDED:
                appended += 1
            else:
                duplicate += 1

        await self._source_repo.mark_polled(source.id, status=PollStatus.OK)

        logger.info(
            "ingested source '{name}': inserted={i} appended={a} duplicate={d} "
            "skipped_for_backfill={s}",
            name=source.name,
            i=inserted,
            a=appended,
            d=duplicate,
            s=skipped,
        )
        return IngestSourceResult(
            source_id=source.id,
            source_name=source.name,
            succeeded=True,
            inserted_count=inserted,
            appended_count=appended,
            duplicate_count=duplicate,
            skipped_for_backfill=skipped,
        )
