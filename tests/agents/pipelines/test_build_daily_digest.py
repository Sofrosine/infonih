from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from infonih.agents.pipelines.build_daily_digest import BuildDailyDigestPipeline
from infonih.domain.article import Article, ArticleStatus


class FakeAnthropic:
    def __init__(self, summaries: list[str] | None = None) -> None:
        self._summaries = list(summaries) if summaries else []
        self.calls = 0

    async def complete_text(self, **_kwargs) -> str:
        self.calls += 1
        if self._summaries:
            return self._summaries.pop(0)
        return "default summary"

    async def complete_structured(self, **_):  # pragma: no cover
        raise NotImplementedError


class FakeArticleRepo:
    def __init__(self, candidates: list[Article]) -> None:
        self._candidates = list(candidates)
        self.marked_sent: list[UUID] = []

    async def list_digest_candidates(self, **_kwargs) -> list[Article]:
        return self._candidates

    async def mark_sent_in_digest(self, ids: list[UUID], *, sent_at: datetime) -> None:
        self.marked_sent = list(ids)

    # Stubs.
    async def insert_or_append_source(self, **_):  # pragma: no cover
        raise NotImplementedError

    async def find_by_url(self, *_args, **_kwargs):  # pragma: no cover
        return None

    async def list_unscored(self, **_):  # pragma: no cover
        return []

    async def mark_scored(self, *_args, **_kwargs):  # pragma: no cover
        pass

    async def mark_score_failed(self, *_args, **_kwargs):  # pragma: no cover
        pass


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> int | None:
        self.sent.append(text)
        return 42


def _scored(score: int, *, title: str | None = None) -> Article:
    now = datetime.now(UTC)
    return Article(
        id=uuid4(),
        url_normalized=f"https://example.com/{score}",
        url_original=f"https://example.com/{score}",
        title=title or f"Article {score}",
        raw_content="content",
        published_at=now - timedelta(hours=2),
        sources=["Example"],
        status=ArticleStatus.SCORED,
        score=score,
        created_at=now,
        updated_at=now,
    )


async def test_run_sends_low_signal_message_when_no_candidates() -> None:
    repo = FakeArticleRepo([])
    telegram = FakeTelegram()
    pipeline = BuildDailyDigestPipeline(
        anthropic=FakeAnthropic(),
        article_repo=repo,
        telegram=telegram,
    )

    result = await pipeline.run()

    assert result.item_count == 0
    assert result.sent is True
    assert result.skip_reason == "low_signal"
    assert "Low-signal day" in telegram.sent[0]
    assert repo.marked_sent == []


async def test_run_summarises_and_sends_top_items() -> None:
    repo = FakeArticleRepo([_scored(90), _scored(80), _scored(60)])
    telegram = FakeTelegram()
    pipeline = BuildDailyDigestPipeline(
        anthropic=FakeAnthropic(["sum1", "sum2", "sum3"]),
        article_repo=repo,
        telegram=telegram,
    )

    result = await pipeline.run()

    assert result.item_count == 3
    assert "Article 90" in telegram.sent[0]
    assert "sum1" in telegram.sent[0]
    assert len(repo.marked_sent) == 3


async def test_run_caps_at_digest_max_items(monkeypatch) -> None:
    from infonih.agents.pipelines import build_daily_digest as mod

    monkeypatch.setattr(mod.settings, "digest_max_items", 2)
    repo = FakeArticleRepo([_scored(90), _scored(80), _scored(60), _scored(55)])
    telegram = FakeTelegram()
    pipeline = BuildDailyDigestPipeline(
        anthropic=FakeAnthropic(["a", "b"]),
        article_repo=repo,
        telegram=telegram,
    )

    result = await pipeline.run()

    assert result.item_count == 2
    assert len(repo.marked_sent) == 2
