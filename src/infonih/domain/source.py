from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from infonih.domain.category import Category


class SourceType(StrEnum):
    RSS = "rss"


class PollStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class Source(BaseModel):
    """A configured news source the user wants infonih to poll.

    The runtime source of truth lives in the `sources` table. This pure
    Pydantic model is the in-memory representation passed between layers.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    type: SourceType
    url: HttpUrl
    category: Category
    weight: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0.1"), le=Decimal("10.0"))
    poll_interval_minutes: int = Field(default=60, ge=1)
    enabled: bool = True
    last_polled_at: datetime | None = None
    last_poll_status: PollStatus | None = None
    last_poll_error: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
