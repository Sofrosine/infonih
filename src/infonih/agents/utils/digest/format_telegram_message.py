"""Format a list of selected articles into a Telegram-ready HTML message.

Per FLOWS.md §216: header with date, sections by category, each item with
title, source, summary, link, and item number for reactions.
"""

from datetime import date
from html import escape

from infonih.domain.article import Article


def format_digest(
    *,
    items: list[tuple[Article, str]],
    digest_date: date,
) -> str:
    """`items` is `[(article, summary)]` already sorted in send order."""
    header = f"<b>📰 infonih — {digest_date.isoformat()}</b>"
    if not items:
        return f"{header}\n\nLow-signal day — nothing met the threshold."

    lines = [header]
    for i, (article, summary) in enumerate(items, start=1):
        source_label = ", ".join(article.sources) if article.sources else "unknown"
        title_link = (
            f'<a href="{escape(str(article.url_original))}">{escape(article.title)}</a>'
        )
        lines.append(
            f"\n<b>{i}. {title_link}</b>\n"
            f"<i>{escape(source_label)} · score {article.score}</i>\n"
            f"{escape(summary)}"
        )
    return "\n".join(lines)
