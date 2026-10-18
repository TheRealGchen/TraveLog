"""Fetch a link's preview (title, image, icon) when it is pinned.

The API fetches user-supplied URLs, so it guards against server-side request forgery: only
http(s) URLs whose host resolves to public addresses are fetched, every redirect hop is checked
the same way, and responses are capped in time and size. Any failure just means no preview.
"""

import asyncio
import contextlib
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 512 * 1024
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(5.0)
USER_AGENT = "Mozilla/5.0 (compatible; TravelPlannerLinkPreview/1.0)"


@dataclass(frozen=True)
class LinkPreview:
    title: str | None
    image_url: str | None
    icon_url: str | None


PreviewFetcher = Callable[[str], Awaitable[LinkPreview | None]]


class _MetaParser(HTMLParser):
    """Collects <title>, Open Graph/Twitter meta tags, and icon links from a page's HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.icons: list[tuple[str, str]] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "link" and a.get("href"):
            rel = a.get("rel", "").lower()
            if "icon" in rel.split() or "apple-touch-icon" in rel:
                self.icons.append((rel, a["href"]))
        elif tag == "title" and not self.title:
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def parse_preview(html: str, page_url: str) -> LinkPreview:
    """Pull a title, preview image, and icon out of a page, resolving relative URLs."""
    parser = _MetaParser()
    # Malformed HTML still yields whatever was parsed before the error.
    with contextlib.suppress(Exception):
        parser.feed(html)
    meta = parser.meta
    title = meta.get("og:title") or meta.get("twitter:title") or " ".join(parser.title.split())
    image = meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image")
    # Prefer the largest touch icon, then any icon, then the conventional /favicon.ico.
    icons = sorted(parser.icons, key=lambda icon: "apple-touch-icon" not in icon[0])
    icon = icons[0][1] if icons else "/favicon.ico"
    return LinkPreview(
        title=title[:200] or None,
        image_url=_absolute(image, page_url),
        icon_url=_absolute(icon, page_url),
    )


def _absolute(url: str | None, base: str) -> str | None:
    if not url:
        return None
    resolved = urljoin(base, url.strip())
    return resolved if urlsplit(resolved).scheme in ("http", "https") else None


async def is_public_host(host: str) -> bool:
    """True if every address ``host`` resolves to is a public (globally routable) address."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    return bool(addresses) and all(a.is_global and not a.is_multicast for a in addresses)


async def fetch_preview(url: str) -> LinkPreview | None:
    """Fetch ``url`` and return its preview, or None if it can't be fetched safely."""
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": USER_AGENT}
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                parts = urlsplit(url)
                if parts.scheme not in ("http", "https") or not parts.hostname:
                    return None
                if not await is_public_host(parts.hostname):
                    return None
                async with client.stream("GET", url) as response:
                    if response.is_redirect and "location" in response.headers:
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        return None
                    if "html" not in response.headers.get("content-type", ""):
                        return None
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) >= MAX_BYTES:
                            break
                    html = body.decode(response.encoding or "utf-8", errors="replace")
                    return parse_preview(html, str(response.url))
    except httpx.HTTPError, ValueError, UnicodeError:
        return None
    return None


async def no_preview(url: str) -> LinkPreview | None:
    """Fetcher used when previews are turned off (LINK_PREVIEWS=false)."""
    return None
