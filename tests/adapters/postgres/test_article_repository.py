from datetime import UTC, datetime, timedelta

from infonih.adapters.postgres.article_repository import PostgresArticleRepository
from infonih.domain.repositories.article_repository import IngestOutcome


async def _ingest(
    repo: PostgresArticleRepository,
    *,
    url: str = "https://example.com/article-1",
    title: str = "First article",
    source_name: str = "Example",
    published_at: datetime | None = None,
    raw_content: str | None = "summary",
    is_backfill: bool = False,
):
    return await repo.insert_or_append_source(
        url_normalized=url,
        url_original=url,
        title=title,
        published_at=published_at or datetime(2026, 4, 27, 12, tzinfo=UTC),
        source_name=source_name,
        raw_content=raw_content,
        is_backfill=is_backfill,
    )


async def test_insert_or_append_source_inserts_new_article(
    article_repo: PostgresArticleRepository,
) -> None:
    result = await _ingest(article_repo)

    assert result.outcome is IngestOutcome.INSERTED


async def test_insert_or_append_source_appends_new_source_to_existing(
    article_repo: PostgresArticleRepository,
) -> None:
    await _ingest(article_repo, source_name="Source A")

    result = await _ingest(article_repo, source_name="Source B")

    assert result.outcome is IngestOutcome.SOURCE_APPENDED
    article = await article_repo.find_by_url("https://example.com/article-1")
    assert article is not None
    assert sorted(article.sources) == ["Source A", "Source B"]


async def test_insert_or_append_source_returns_duplicate_when_source_already_present(
    article_repo: PostgresArticleRepository,
) -> None:
    await _ingest(article_repo, source_name="Source A")

    result = await _ingest(article_repo, source_name="Source A")

    assert result.outcome is IngestOutcome.DUPLICATE
    article = await article_repo.find_by_url("https://example.com/article-1")
    assert article is not None
    assert article.sources == ["Source A"]


async def test_insert_or_append_source_three_sources_same_url(
    article_repo: PostgresArticleRepository,
) -> None:
    await _ingest(article_repo, source_name="A")
    await _ingest(article_repo, source_name="B")
    await _ingest(article_repo, source_name="C")

    article = await article_repo.find_by_url("https://example.com/article-1")
    assert article is not None
    assert sorted(article.sources) == ["A", "B", "C"]


async def test_find_by_url_returns_none_when_missing(
    article_repo: PostgresArticleRepository,
) -> None:
    found = await article_repo.find_by_url("https://nope.example/x")

    assert found is None


async def test_list_unscored_orders_newest_first(
    article_repo: PostgresArticleRepository,
) -> None:
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    await _ingest(
        article_repo,
        url="https://example.com/old",
        published_at=now - timedelta(days=2),
    )
    await _ingest(
        article_repo,
        url="https://example.com/new",
        published_at=now,
    )

    articles = await article_repo.list_unscored()

    assert [a.url_normalized for a in articles] == [
        "https://example.com/new",
        "https://example.com/old",
    ]


async def test_list_unscored_respects_limit(
    article_repo: PostgresArticleRepository,
) -> None:
    for i in range(5):
        await _ingest(article_repo, url=f"https://example.com/a{i}")

    articles = await article_repo.list_unscored(limit=3)

    assert len(articles) == 3
