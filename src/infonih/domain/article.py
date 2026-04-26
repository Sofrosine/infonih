from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ArticleStatus(StrEnum):
    UNSCORED = "unscored"
    SCORED = "scored"
    SCORE_FAILED = "score_failed"


class Article(BaseModel):
    """An ingested article. Identity is `url_normalized` (unique per user).

    Scoring fields populate when the article transitions to `scored` /
    `score_failed`. The `sources` list grows as multiple feeds surface the
    same URL — never duplicate, append-only by name.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID | None = None
    url_normalized: str = Field(min_length=1)
    url_original: HttpUrl
    title: str = Field(min_length=1)
    raw_content: str | None = None
    published_at: datetime
    sources: list[str] = Field(default_factory=list)
    status: ArticleStatus = ArticleStatus.UNSCORED
    score: int | None = Field(default=None, ge=0, le=100)
    score_reasoning: str | None = None
    low_content_confidence: bool = False
    scored_at: datetime | None = None
    scored_with_interest_version: int | None = None
    score_failure_reason: str | None = None
    is_backfill: bool = False
    sent_in_digest_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
