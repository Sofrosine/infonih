import pytest

from infonih.agents.utils.url.normalize_url import normalize_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Lowercases scheme and host.
        (
            "HTTPS://Example.COM/Path",
            "https://example.com/Path",
        ),
        # Strips fragment.
        (
            "https://example.com/article#section-2",
            "https://example.com/article",
        ),
        # Strips utm_* params and sorts the rest.
        (
            "https://example.com/x?utm_source=twitter&utm_medium=social&id=42",
            "https://example.com/x?id=42",
        ),
        # Strips fbclid / gclid.
        (
            "https://example.com/x?fbclid=abc&gclid=def&keep=1",
            "https://example.com/x?keep=1",
        ),
        # Drops trailing slash but keeps root "/".
        (
            "https://example.com/path/",
            "https://example.com/path",
        ),
        (
            "https://example.com/",
            "https://example.com/",
        ),
        # Drops default ports.
        (
            "http://example.com:80/",
            "http://example.com/",
        ),
        (
            "https://example.com:443/x",
            "https://example.com/x",
        ),
        # Preserves non-default ports.
        (
            "https://example.com:8443/x",
            "https://example.com:8443/x",
        ),
        # Idempotent.
        (
            "https://example.com/article?id=1",
            "https://example.com/article?id=1",
        ),
    ],
)
def test_normalize_url_returns_canonical_form(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_normalize_url_is_idempotent() -> None:
    raw = "HTTPS://Example.COM/Path/?utm_source=x&id=1#frag"

    once = normalize_url(raw)
    twice = normalize_url(once)

    assert once == twice
