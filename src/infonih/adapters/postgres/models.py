from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from infonih.domain.article import ArticleStatus
from infonih.domain.category import Category
from infonih.domain.source import PollStatus, SourceType


class Base(DeclarativeBase):
    """SQLAlchemy declarative base. All ORM models inherit this."""


def _enum_values(enum_cls: type) -> list[str]:
    """Use StrEnum values (lowercase) for the Postgres ENUM type, not member names."""
    return [member.value for member in enum_cls]


class SourceModel(Base):
    """Per-flows.md: scheduler picks "due" sources by (enabled, last_polled_at).
    UNIQUE constraints enforce dedup; no other indexes — sources is small."""

    __tablename__ = "sources"
    __table_args__ = (
        # NULLS NOT DISTINCT: single-user mode stores user_id=NULL on every row;
        # without this, two NULLs would not collide and dedup would silently fail.
        UniqueConstraint(
            "user_id", "url", name="uq_sources_user_url", postgresql_nulls_not_distinct=True
        ),
        UniqueConstraint(
            "user_id", "name", name="uq_sources_user_name", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint("weight >= 0.1 AND weight <= 10.0", name="ck_sources_weight_range"),
        CheckConstraint("poll_interval_minutes >= 1", name="ck_sources_poll_interval_min"),
        CheckConstraint("consecutive_failures >= 0", name="ck_sources_failures_nonneg"),
        Index("ix_sources_enabled_last_polled", "enabled", "last_polled_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", values_callable=_enum_values),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Category] = mapped_column(
        SAEnum(Category, name="category", values_callable=_enum_values),
        nullable=False,
    )
    weight: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default=text("1.0")
    )
    poll_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_poll_status: Mapped[PollStatus | None] = mapped_column(
        SAEnum(PollStatus, name="poll_status", values_callable=_enum_values),
        nullable=True,
    )
    last_poll_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ArticleModel(Base):
    """Per-flows.md: scorer scans WHERE status='unscored'; UNIQUE enforces dedup.
    Other indexes deferred until query patterns prove they're hot."""

    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "url_normalized",
            name="uq_articles_user_url",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)",
            name="ck_articles_score_range",
        ),
        Index("ix_articles_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    url_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    url_original: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status", values_callable=_enum_values),
        nullable=False,
        server_default=text("'unscored'"),
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    low_content_confidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scored_with_interest_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_backfill: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sent_in_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    settings_version_link: Mapped["UserSettingsModel | None"] = relationship(
        primaryjoin=(
            "foreign(ArticleModel.scored_with_interest_version) "
            "== UserSettingsModel.interests_version"
        ),
        viewonly=True,
        uselist=False,
    )


class UserSettingsModel(Base):
    """Single-row table in single-user mode. Only the UNIQUE on user_id is needed."""

    __tablename__ = "user_settings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", name="uq_user_settings_user", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint(
            "score_threshold BETWEEN 0 AND 100",
            name="ck_user_settings_score_threshold_range",
        ),
        CheckConstraint("digest_max_items >= 1", name="ck_user_settings_max_items_min"),
        CheckConstraint("interests_version >= 1", name="ck_user_settings_version_min"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    interests_text: Mapped[str] = mapped_column(Text, nullable=False)
    interests_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    digest_time_local: Mapped[str] = mapped_column(
        String(5), nullable=False, server_default=text("'07:00'")
    )
    digest_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'Asia/Jakarta'")
    )
    score_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("50")
    )
    digest_max_items: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("7")
    )
    category_caps: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    paused_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CostEventModel(Base):
    """Append-only audit log of LLM costs.

    No FK on `article_id` so deleting articles never blocks cleanup; orphan
    rows are valid (they record that we paid for an article that's now gone).
    """

    __tablename__ = "cost_events"
    __table_args__ = (
        # Daily / weekly / monthly summaries scan by created_at; the
        # /cost command's hot path. (flow, created_at) gives free
        # per-flow rollups using the same B-tree.
        Index("ix_cost_events_flow_created_at", "flow", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    flow: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_creation_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cache_read_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    article_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
