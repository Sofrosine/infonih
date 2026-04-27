from datetime import UTC, date, datetime
from uuid import uuid4

from infonih.agents.utils.digest.format_telegram_message import format_digest
from infonih.domain.article import Article, ArticleStatus


def _article(*, title: str, sources: list[str], score: int = 70) -> Article:
    now = datetime(2026, 4, 27, 12, tzinfo=UTC)
    return Article(
        id=uuid4(),
        url_normalized="https://example.com/x",
        url_original="https://example.com/x",
        title=title,
        published_at=now,
        sources=sources,
        status=ArticleStatus.SCORED,
        score=score,
        created_at=now,
        updated_at=now,
    )


def test_format_digest_empty_returns_low_signal() -> None:
    msg = format_digest(items=[], digest_date=date(2026, 4, 27))
    assert "Low-signal day" in msg
    assert "2026-04-27" in msg


def test_format_digest_numbers_and_links_items() -> None:
    items = [
        (_article(title="First", sources=["A"], score=90), "Summary one."),
        (_article(title="Second", sources=["B", "C"], score=72), "Summary two."),
    ]

    msg = format_digest(items=items, digest_date=date(2026, 4, 27))

    assert "1." in msg and "First" in msg
    assert "2." in msg and "Second" in msg
    assert "B, C" in msg
    assert "Summary one." in msg


def test_format_digest_escapes_html_in_titles() -> None:
    items = [(_article(title="<script>alert(1)</script>", sources=["A"]), "ok")]

    msg = format_digest(items=items, digest_date=date(2026, 4, 27))

    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg
