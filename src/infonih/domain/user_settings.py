from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from infonih.domain.category import Category


class UserSettings(BaseModel):
    """Per-user preferences mutated via Telegram commands.

    Single-row in single-user mode (`user_id is None` is the singleton).
    `interests_version` increments on every interests update; articles
    record which version scored them for auditability.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    user_id: UUID | None = None
    interests_text: str = Field(min_length=1)
    interests_version: int = Field(default=1, ge=1)
    digest_time_local: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    digest_timezone: str = Field(default="Asia/Jakarta")
    score_threshold: int = Field(default=50, ge=0, le=100)
    digest_max_items: int = Field(default=7, ge=1)
    category_caps: dict[Category, int] = Field(default_factory=dict)
    paused_until: datetime | None = None
    created_at: datetime
    updated_at: datetime
