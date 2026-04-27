from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from infonih.adapters.anthropic_adapter import AnthropicError
from infonih.agents.pipelines.score_articles import ScoreArticlesPipeline
from infonih.agents.schemas.article_score_schema import ArticleScoreSchema
from infonih.domain.article import Article, ArticleStatus
from infonih.domain.user_settings import UserSettings


class FakeAnthropic:
    def __init__(self) -> None:
        self.responses: list[ArticleScoreSchema | Exception] = []
        self.calls: list[dict] = []

    async def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return ArticleScoreSchema(score=42, reasoning="default reasoning")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeArticleRepo:
    def __init__(self, articles: list[Article]) -> None:
        self._articles = list(articles)
        self.scored: list[dict] = []
        self.failed: list[dict] = []

    async def list_unscored(self, *, limit: int = 100, user_id=None) -> list[Article]:
        return self._articles[:limit]

    async def mark_scored(self, article_id: UUID, **kwargs) -> None:
        self.scored.append({"article_id": article_id, **kwargs})

    async def mark_score_failed(self, article_id: UUID, *, reason: str) -> None:
        self.failed.append({"article_id": article_id, "reason": reason})

    # Unused stubs.
    async def insert_or_append_source(self, **_):  # pragma: no cover
        raise NotImplementedError

    async def find_by_url(self, *_args, **_kwargs):  # pragma: no cover
        return None

    async def list_digest_candidates(self, **_):  # pragma: no cover
        return []

    async def mark_sent_in_digest(self, *_args, **_kwargs):  # pragma: no cover
        pass


class FakeUserSettings:
    def __init__(self, settings: UserSettings | None) -> None:
        self._settings = settings

    async def get(self, *, user_id=None) -> UserSettings | None:
        return self._settings

    async def set_interests(self, *_args, **_kwargs):  # pragma: no cover
        raise NotImplementedError


def _settings() -> UserSettings:
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    return UserSettings(
        id=uuid4(),
        interests_text="AI engineering, AI policy",
        interests_version=3,
        created_at=now,
        updated_at=now,
    )


def _article(*, title: str = "An article") -> Article:
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    return Article(
        id=uuid4(),
        url_normalized="https://example.com/a",
        url_original="https://example.com/a",
        title=title,
        raw_content="Some content about AI.",
        published_at=now,
        sources=["Example"],
        status=ArticleStatus.UNSCORED,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def anthropic_fake() -> FakeAnthropic:
    return FakeAnthropic()


async def test_run_skips_when_no_user_settings(anthropic_fake: FakeAnthropic) -> None:
    pipeline = ScoreArticlesPipeline(
        anthropic=anthropic_fake,
        article_repo=FakeArticleRepo([_article()]),
        user_settings_repo=FakeUserSettings(None),
    )

    result = await pipeline.run()

    assert result.skipped is True
    assert result.skip_reason == "no_user_settings"
    assert anthropic_fake.calls == []


async def test_run_scores_articles_and_persists(anthropic_fake: FakeAnthropic) -> None:
    article = _article()
    article_repo = FakeArticleRepo([article])
    anthropic_fake.responses = [
        ArticleScoreSchema(score=78, reasoning="strong AI engineering match.")
    ]
    pipeline = ScoreArticlesPipeline(
        anthropic=anthropic_fake,
        article_repo=article_repo,
        user_settings_repo=FakeUserSettings(_settings()),
    )

    result = await pipeline.run()

    assert result.scored == 1
    assert result.failed == 0
    assert article_repo.scored[0]["score"] == 78
    assert article_repo.scored[0]["interests_version"] == 3


async def test_run_marks_score_failed_on_anthropic_error(
    anthropic_fake: FakeAnthropic,
) -> None:
    article = _article()
    article_repo = FakeArticleRepo([article])
    anthropic_fake.responses = [AnthropicError("rate limited")]
    pipeline = ScoreArticlesPipeline(
        anthropic=anthropic_fake,
        article_repo=article_repo,
        user_settings_repo=FakeUserSettings(_settings()),
    )

    result = await pipeline.run()

    assert result.scored == 0
    assert result.failed == 1
    assert article_repo.failed[0]["reason"] == "rate limited"


async def test_run_returns_zero_when_no_unscored(anthropic_fake: FakeAnthropic) -> None:
    pipeline = ScoreArticlesPipeline(
        anthropic=anthropic_fake,
        article_repo=FakeArticleRepo([]),
        user_settings_repo=FakeUserSettings(_settings()),
    )

    result = await pipeline.run()

    assert result.scored == 0
    assert result.failed == 0
    assert result.skipped is False
