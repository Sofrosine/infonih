from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from infonih.adapters.rss_adapter import RssAdapter, RssFetchError

# ---------------------------------------------------------------------------
# Fixtures: canned RSS / Atom XML and a helper that builds an adapter wired
# to a MockTransport that returns whatever the test specifies.
# ---------------------------------------------------------------------------

RSS_2_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <link>https://example.com/</link>
    <description>An example RSS feed</description>
    <item>
      <title>First article</title>
      <link>https://example.com/first</link>
      <description>The summary of the first article.</description>
      <pubDate>Mon, 27 Apr 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second article</title>
      <link>https://example.com/second</link>
      <description>The summary of the second.</description>
      <pubDate>Mon, 27 Apr 2026 09:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <link href="https://atom.example/"/>
  <updated>2026-04-27T10:00:00Z</updated>
  <id>https://atom.example/</id>
  <entry>
    <title>Atom Item</title>
    <link href="https://atom.example/post-1"/>
    <id>https://atom.example/post-1</id>
    <updated>2026-04-27T10:00:00Z</updated>
    <published>2026-04-27T10:00:00Z</published>
    <content type="html">&lt;p&gt;Atom content body.&lt;/p&gt;</content>
  </entry>
</feed>
"""

MISSING_DATE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Bad Feed</title>
    <link>https://bad.example/</link>
    <description>A feed whose entry has no date.</description>
    <item>
      <title>No date</title>
      <link>https://bad.example/no-date</link>
      <description>summary</description>
    </item>
    <item>
      <title>Has date</title>
      <link>https://bad.example/dated</link>
      <description>summary</description>
      <pubDate>Mon, 27 Apr 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

EMPTY_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty</title>
    <link>https://empty.example/</link>
    <description>No items.</description>
  </channel>
</rss>
"""


def _adapter_with(handler: Callable[[httpx.Request], httpx.Response]) -> RssAdapter:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return RssAdapter(client=client)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_fetch_parses_rss_2_entries() -> None:
    adapter = _adapter_with(lambda _: httpx.Response(200, content=RSS_2_FEED))

    entries = await adapter.fetch("https://example.com/feed.xml")

    assert len(entries) == 2
    assert str(entries[0].url) == "https://example.com/first"
    assert entries[0].title == "First article"
    assert entries[0].published_at == datetime(2026, 4, 27, 8, 0, tzinfo=UTC)
    assert entries[0].raw_content == "The summary of the first article."


async def test_fetch_parses_atom_entries() -> None:
    adapter = _adapter_with(lambda _: httpx.Response(200, content=ATOM_FEED))

    entries = await adapter.fetch("https://atom.example/feed.xml")

    assert len(entries) == 1
    assert str(entries[0].url) == "https://atom.example/post-1"
    assert entries[0].title == "Atom Item"
    assert entries[0].published_at == datetime(2026, 4, 27, 10, 0, tzinfo=UTC)
    assert entries[0].raw_content is not None
    assert "Atom content body" in entries[0].raw_content


async def test_fetch_drops_entries_missing_date() -> None:
    adapter = _adapter_with(lambda _: httpx.Response(200, content=MISSING_DATE_RSS))

    entries = await adapter.fetch("https://bad.example/feed.xml")

    assert [str(e.url) for e in entries] == ["https://bad.example/dated"]


async def test_fetch_returns_empty_list_for_empty_feed() -> None:
    adapter = _adapter_with(lambda _: httpx.Response(200, content=EMPTY_FEED))

    entries = await adapter.fetch("https://empty.example/feed.xml")

    assert entries == []


async def test_fetch_raises_on_http_error() -> None:
    adapter = _adapter_with(lambda _: httpx.Response(404, content=b"not found"))

    with pytest.raises(RssFetchError, match="HTTP error"):
        await adapter.fetch("https://gone.example/feed.xml")


async def test_fetch_raises_on_unparseable_body() -> None:
    adapter = _adapter_with(
        lambda _: httpx.Response(200, content=b"<!DOCTYPE html><html>not a feed</html>")
    )

    with pytest.raises(RssFetchError, match="could not be parsed"):
        await adapter.fetch("https://html.example/page.html")


async def test_fetch_raises_on_timeout() -> None:
    def _timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout")

    adapter = _adapter_with(_timeout)

    with pytest.raises(RssFetchError, match="HTTP error"):
        await adapter.fetch("https://slow.example/feed.xml")
