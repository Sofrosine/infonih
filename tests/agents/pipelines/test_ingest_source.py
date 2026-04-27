from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from infonih.adapters.rss_adapter import RssFetchError
from infonih.agents.pipelines.ingest_source import IngestSourcePipeline
from infonih.domain.category import Category
from infonih.domain.feed_entry import FeedEntry
from infonih.domain.repositories.article_repository import IngestOutcome, IngestResult
from infonih.domain.source import PollStatus, Source, SourceType

# ---------------------------------------------------------------------------
# In-memory fakes — mock the *adapters* (per CLAUDE.md), not feedparser/SQLAlchemy.
# ---------------------------------------------------------------------------


class FakeRssAdapter:
    def __init__(self, entries: list[FeedEntry] | None = None) -> None:
        self.entries = entries or []
        self.error: RssFetchError | None = None
        self.fetched_urls: list[str] = []

    async def fetch(self, url: str) -> list[FeedEntry]:
        self.fetched_urls.append(url)
        if self.error is not None:
            raise self.error
        return list(self.entries)


class FakeArticleRepository:
    def __init__(self, outcomes: list[IngestOutcome] | None = None) -> None:
        self._outcomes = list(outcomes) if outcomes else []
        self.calls: list[dict] = []

    async def insert_or_append_source(self, **kwargs) -> IngestResult:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0) if self._outcomes else IngestOutcome.INSERTED
        return IngestResult(article_id=uuid4(), outcome=outcome)

    async def find_by_url(self, *_args, **_kwargs):
        return None

    async def list_unscored(self, *_args, **_kwargs):
        return []


class FakeSourceRepository:
    def __init__(self) -> None:
        self.poll_marks: list[dict] = []

    async def mark_polled(
        self, source_id: UUID, *, status: PollStatus, error: str | None = None
    ) -> None:
        self.poll_marks.append({"source_id": source_id, "status": status, "error": error})

    # Unused stubs to satisfy the Protocol shape.
    async def add(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def list_enabled(self, **kwargs):  # pragma: no cover
        return []

    async def get_by_name(self, *_args, **_kwargs):  # pragma: no cover
        return None

    async def pause(self, *_args, **_kwargs):  # pragma: no cover
        pass

    async def resume(self, *_args, **_kwargs):  # pragma: no cover
        pass

    async def remove(self, *_args, **_kwargs):  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(*, last_polled_at: datetime | None = None) -> Source:
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    return Source(
        id=uuid4(),
        name="Example",
        type=SourceType.RSS,
        url="https://example.com/feed.xml",
        category=Category.AI_ENGINEERING,
        weight=Decimal("1.0"),
        poll_interval_minutes=60,
        enabled=True,
        last_polled_at=last_polled_at,
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
    )


def _entry(url: str, *, published_at: datetime | None = None) -> FeedEntry:
    return FeedEntry(
        url=url,
        title=f"Title for {url}",
        raw_content="content",
        published_at=published_at or datetime(2026, 4, 27, 8, tzinfo=UTC),
    )


@pytest.fixture
def rss() -> FakeRssAdapter:
    return FakeRssAdapter()


@pytest.fixture
def article_repo() -> FakeArticleRepository:
    return FakeArticleRepository()


@pytest.fixture
def source_repo() -> FakeSourceRepository:
    return FakeSourceRepository()


@pytest.fixture
def pipeline(
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
    source_repo: FakeSourceRepository,
) -> IngestSourcePipeline:
    return IngestSourcePipeline(
        rss=rss, article_repo=article_repo, source_repo=source_repo
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_run_counts_outcomes_correctly(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    rss.entries = [_entry("https://example.com/a"), _entry("https://example.com/b"), _entry("https://example.com/c")]
    article_repo._outcomes = [
        IngestOutcome.INSERTED,
        IngestOutcome.SOURCE_APPENDED,
        IngestOutcome.DUPLICATE,
    ]

    result = await pipeline.run(_make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC)))

    assert result.succeeded is True
    assert result.inserted_count == 1
    assert result.appended_count == 1
    assert result.duplicate_count == 1
    assert result.skipped_for_backfill == 0


async def test_run_normalizes_url_before_insert(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    # Note: Pydantic's HttpUrl validator already lowercases scheme + host on
    # parse, so by the time the URL reaches the pipeline, that part of
    # normalization has already happened. The pipeline's own normalize_url
    # call still strips utm_*, drops the fragment, and removes trailing /.
    rss.entries = [
        _entry("HTTPS://Example.COM/path/?utm_source=twitter&id=42#section")
    ]

    await pipeline.run(_make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC)))

    assert article_repo.calls[0]["url_normalized"] == "https://example.com/path?id=42"
    assert (
        article_repo.calls[0]["url_original"]
        == "https://example.com/path/?utm_source=twitter&id=42#section"
    )


async def test_run_marks_source_polled_ok_on_success(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    source_repo: FakeSourceRepository,
) -> None:
    rss.entries = [_entry("https://example.com/a")]
    source = _make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC))

    await pipeline.run(source)

    assert source_repo.poll_marks == [
        {"source_id": source.id, "status": PollStatus.OK, "error": None}
    ]


async def test_run_marks_source_polled_failed_on_fetch_error(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
    source_repo: FakeSourceRepository,
) -> None:
    rss.error = RssFetchError("connection refused")
    source = _make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC))

    result = await pipeline.run(source)

    assert result.succeeded is False
    assert result.error == "connection refused"
    assert article_repo.calls == []
    assert source_repo.poll_marks == [
        {"source_id": source.id, "status": PollStatus.FAILED, "error": "connection refused"}
    ]


async def test_first_poll_skips_articles_older_than_backfill_window(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    now = datetime.now(UTC)
    rss.entries = [
        _entry("https://example.com/old", published_at=now - timedelta(days=30)),
        _entry("https://example.com/recent", published_at=now - timedelta(days=2)),
    ]

    result = await pipeline.run(_make_source(last_polled_at=None))

    assert result.skipped_for_backfill == 1
    assert len(article_repo.calls) == 1
    assert article_repo.calls[0]["url_original"] == "https://example.com/recent"


async def test_first_poll_marks_ingested_articles_as_backfill(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    rss.entries = [_entry("https://example.com/a")]

    await pipeline.run(_make_source(last_polled_at=None))

    assert article_repo.calls[0]["is_backfill"] is True


async def test_subsequent_poll_does_not_set_backfill(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    rss.entries = [_entry("https://example.com/a")]

    await pipeline.run(_make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC)))

    assert article_repo.calls[0]["is_backfill"] is False


async def test_subsequent_poll_does_not_apply_age_filter(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    very_old = datetime.now(UTC) - timedelta(days=365)
    rss.entries = [_entry("https://example.com/old", published_at=very_old)]

    result = await pipeline.run(
        _make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC))
    )

    assert result.skipped_for_backfill == 0
    assert len(article_repo.calls) == 1


async def test_run_passes_source_user_id_for_multi_tenancy(
    pipeline: IngestSourcePipeline,
    rss: FakeRssAdapter,
    article_repo: FakeArticleRepository,
) -> None:
    rss.entries = [_entry("https://example.com/a")]
    source = _make_source(last_polled_at=datetime(2026, 4, 1, tzinfo=UTC))

    await pipeline.run(source)

    assert article_repo.calls[0]["user_id"] == source.user_id  # None today, future-proof
