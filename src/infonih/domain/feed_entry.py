from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class FeedEntry(BaseModel):
    """A normalized entry from any feed source (RSS, Atom, future API fetchers).

    The fetcher's only job is to produce these. The pipeline normalizes the
    URL, attaches a source name, and writes to the articles table.
    """

    model_config = ConfigDict(frozen=True)

    url: HttpUrl
    title: str = Field(min_length=1)
    raw_content: str | None = None
    published_at: datetime
