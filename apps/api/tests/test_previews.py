import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from travel_api import previews
from travel_api.previews import fetch_preview, is_public_host, parse_preview

PAGE = """<!doctype html><html><head>
<title>  Tokyo   Guide </title>
<meta property="og:title" content="Tokyo Travel Guide">
<meta property="og:image" content="/img/tokyo.jpg">
<link rel="icon" href="/favicon-32.png">
<link rel="apple-touch-icon" href="https://cdn.example.com/touch.png">
</head><body>hi</body></html>"""


def test_parse_prefers_open_graph_and_resolves_urls() -> None:
    p = parse_preview(PAGE, "https://example.com/tokyo/guide")
    assert p.title == "Tokyo Travel Guide"
    assert p.image_url == "https://example.com/img/tokyo.jpg"
    assert p.icon_url == "https://cdn.example.com/touch.png"


def test_parse_falls_back_to_title_tag_and_favicon() -> None:
    p = parse_preview("<html><head><title> Plain \n page </title></head></html>", "https://a.com/x")
    assert p.title == "Plain page"
    assert p.image_url is None
    assert p.icon_url == "https://a.com/favicon.ico"


def test_parse_ignores_non_web_image_urls() -> None:
    html = '<meta property="og:image" content="javascript:alert(1)">'
    assert parse_preview(html, "https://a.com/").image_url is None


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "0.0.0.0"],
)
async def test_private_hosts_are_not_public(host: str) -> None:
    assert not await is_public_host(host)


async def test_unresolvable_host_is_not_public() -> None:
    assert not await is_public_host("does-not-exist.invalid")


async def test_fetch_refuses_private_addresses_without_connecting() -> None:
    assert await fetch_preview("http://127.0.0.1:9/") is None
    assert await fetch_preview("http://169.254.169.254/latest/meta-data/") is None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/page":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/to-page":
            self.send_response(302)
            self.send_header("Location", "/page")
            self.end_headers()
        elif self.path == "/to-private":
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.1/secret")
            self.end_headers()
        elif self.path == "/json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def local_site(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A local HTTP server; 127.0.0.1 is treated as public only for these tests."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    async def only_loopback_is_public(host: str) -> bool:
        return host == "127.0.0.1"

    monkeypatch.setattr(previews, "is_public_host", only_loopback_is_public)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def test_fetch_reads_page_and_follows_safe_redirects(local_site: str) -> None:
    p = await fetch_preview(f"{local_site}/to-page")
    assert p is not None and p.title == "Tokyo Travel Guide"
    assert p.image_url == f"{local_site}/img/tokyo.jpg"


async def test_fetch_checks_every_redirect_hop(local_site: str) -> None:
    assert await fetch_preview(f"{local_site}/to-private") is None


async def test_fetch_ignores_non_html_and_errors(local_site: str) -> None:
    assert await fetch_preview(f"{local_site}/json") is None
    assert await fetch_preview(f"{local_site}/missing") is None
