from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAM_PREFIXES: tuple[str, ...] = ("utm_",)
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "yclid",
        "ref",
        "ref_src",
        "ref_url",
        "igshid",
        "_hsenc",
        "_hsmi",
    }
)


def normalize_url(url: str) -> str:
    """Return a canonical form of *url* suitable for dedup keys.

    Rules:
        * Lowercase scheme and host.
        * Drop default ports (80 for http, 443 for https).
        * Strip URL fragment.
        * Strip tracking query params (utm_*, fbclid, gclid, etc.).
        * Sort remaining query params for deterministic ordering.
        * Drop a single trailing slash from the path (but keep "/" for root).

    The function is pure: it does not perform DNS resolution, follow
    redirects, or contact the network.
    """
    parts = urlsplit(url.strip())

    scheme = parts.scheme.lower()
    netloc = parts.hostname.lower() if parts.hostname else ""
    if parts.port is not None and not _is_default_port(scheme, parts.port):
        netloc = f"{netloc}:{parts.port}"
    if parts.username or parts.password:
        userinfo = parts.username or ""
        if parts.password:
            userinfo = f"{userinfo}:{parts.password}"
        netloc = f"{userinfo}@{netloc}"

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    query_pairs.sort()
    query = urlencode(query_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _is_tracking_param(key: str) -> bool:
    lowered = key.lower()
    if lowered in _TRACKING_PARAMS:
        return True
    return any(lowered.startswith(prefix) for prefix in _TRACKING_PARAM_PREFIXES)
