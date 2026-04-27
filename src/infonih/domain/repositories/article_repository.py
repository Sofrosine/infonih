from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from infonih.domain.article import Article


class IngestOutcome(StrEnum):
    """Result of an upsert against the articles table."""

    INSERTED = "inserted"
    SOURCE_APPENDED = "source_appended"
    DUPLICATE = "duplicate"


class IngestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    article_id: UUID
    outcome: IngestOutcome


class ArticleRepository(Protocol):
    """Storage contract for ingested articles."""

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
        """Atomic dedup-aware insert.

        Three outcomes:
            * `INSERTED` — no row matched; a new article was created.
            * `SOURCE_APPENDED` — row already existed; `source_name` was
              appended to the article's `sources` array.
            * `DUPLICATE` — row already existed AND `source_name` was
              already in the array; no change.

        The operation is a single SQL statement and therefore race-safe
        under concurrent ingestion of the same URL.
        """
        ...

    async def find_by_url(
        self, url_normalized: str, *, user_id: UUID | None = None
    ) -> Article | None:
        """Lookup by the normalized URL (the dedup key)."""
        ...

    async def list_unscored(
        self, *, limit: int = 100, user_id: UUID | None = None
    ) -> list[Article]:
        """Articles awaiting LLM scoring. Ordered by `published_at` DESC so
        newer articles get scored first."""
        ...
