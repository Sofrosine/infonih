"""RSS / Atom feed fetcher.

Wraps `feedparser` (sync, mature, lenient) behind an async interface.
HTTP fetch happens via `httpx.AsyncClient`; parsing runs in a worker
thread via `asyncio.to_thread` so we don't block the event loop on
large feeds.

Failure policy: any HTTP error, timeout, or unparseable feed raises
`RssFetchError`. Entries that lack a URL or a publish/update timestamp
are silently dropped (logged at WARNING) — the pipeline can still
proceed with whatever the feed gave us.
"""

import asyncio
import calendar
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx
from loguru import logger

from infonih.domain.feed_entry import FeedEntry

_DEFAULT_TIMEOUT_SECONDS = 30.0
_USER_AGENT = "infonih/0.1 (+https://github.com/Sofrosine/infonih)"


class RssFetchError(Exception):
    """Raised when a feed cannot be fetched or parsed.

    Wraps the original exception (HTTP error, timeout, parse error) so
    callers can log a meaningful message without coupling to httpx /
    feedparser specifics.
    """


class RssAdapter:
    """Singleton RSS / Atom fetcher.

    The constructor accepts an optional `httpx.AsyncClient` so tests can
    inject a `MockTransport`. Production wires the singleton at the
    bottom of this module.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )

    async def fetch(self, url: str) -> list[FeedEntry]:
        """Fetch and parse one feed. Returns the entries it contains.

        Raises:
            RssFetchError: HTTP or parse failure.
        """
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RssFetchError(f"HTTP error fetching {url}: {exc}") from exc

        parsed = await asyncio.to_thread(feedparser.parse, response.content)

        # feedparser is extremely lenient — it will silently return zero entries
        # for HTML pages or JSON without flagging an error. Use `version` (empty
        # string when no feed type was detected) as the "is this a feed at all?"
        # signal. An empty but valid feed still has a populated version.
        if not parsed.version:
            reason = getattr(parsed, "bozo_exception", "body is not a recognized feed")
            raise RssFetchError(f"feed at {url} could not be parsed: {reason}")

        return list(_iter_entries(parsed.entries, source_url=url))

    async def aclose(self) -> None:
        """Close the underlying HTTP client. Call at process shutdown."""
        await self._client.aclose()


def _iter_entries(
    raw_entries: Iterable[dict[str, Any]], *, source_url: str
) -> Iterable[FeedEntry]:
    for raw in raw_entries:
        entry = _parse_entry(raw, source_url=source_url)
        if entry is not None:
            yield entry


def _parse_entry(raw: dict[str, Any], *, source_url: str) -> FeedEntry | None:
    url = raw.get("link")
    if not url:
        logger.warning("dropping feed entry without link from {feed}", feed=source_url)
        return None

    title = (raw.get("title") or "").strip()
    if not title:
        # Fall back to the URL — degraded but lets the article still flow
        # through scoring; better than dropping a real article.
        title = url

    published_at = _extract_published_at(raw)
    if published_at is None:
        logger.warning(
            "dropping feed entry without publish/update timestamp: {url}", url=url
        )
        return None

    raw_content = _extract_content(raw)

    try:
        return FeedEntry(
            url=url,
            title=title,
            raw_content=raw_content,
            published_at=published_at,
        )
    except ValueError as exc:
        logger.warning(
            "dropping feed entry from {feed} that failed validation: {err}",
            feed=source_url,
            err=exc,
        )
        return None


def _extract_published_at(raw: dict[str, Any]) -> datetime | None:
    """Prefer `published_parsed`, fall back to `updated_parsed`. Both are
    UTC time tuples per feedparser; we convert via `calendar.timegm`."""
    parsed = raw.get("published_parsed") or raw.get("updated_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


def _extract_content(raw: dict[str, Any]) -> str | None:
    """Pick the most useful textual representation feedparser found.

    Order of preference: full `content[].value` → `summary` → None. We
    don't strip HTML here; the LLM scorer can handle reasonable amounts
    of markup in `raw_content`.
    """
    content_list = raw.get("content")
    if content_list and isinstance(content_list, list):
        first = content_list[0]
        value = first.get("value") if isinstance(first, dict) else None
        if value:
            return str(value).strip() or None
    summary = raw.get("summary")
    if summary:
        return str(summary).strip() or None
    return None


rss = RssAdapter()
