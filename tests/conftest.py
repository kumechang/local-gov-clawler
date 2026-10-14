from pathlib import Path

import httpx
import pytest

from localgov_crawler.fetcher import Fetcher

FIX = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def make_fetcher(routes: dict[str, httpx.Response | tuple], host: str = "www.city.example.jp") -> Fetcher:
    """routes: パス → Response または (status, content_type, body)。未定義パスは404。"""

    def handler(request: httpx.Request) -> httpx.Response:
        r = routes.get(request.url.path)
        if r is None:
            return httpx.Response(404, text="not found")
        if isinstance(r, tuple):
            status, ctype, body = r
            return httpx.Response(status, headers={"content-type": ctype}, content=body if isinstance(body, bytes) else body.encode("utf-8"))
        return r

    return Fetcher(min_interval=0, transport=httpx.MockTransport(handler))


@pytest.fixture
def city_routes():
    html = "text/html; charset=utf-8"
    return {
        "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /admin/\nSitemap: https://www.city.example.jp/sitemap.xml\n"),
        "/": (200, html, fixture_text("top_city.html")),
        "/sports/shisetsu.html": (200, html, fixture_text("sports_hub.html")),
        "/sitemap.xml": (200, "application/xml", '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://www.city.example.jp/sports/shisetsu.html</loc><lastmod>2025-04-01</lastmod></url><url><loc>https://www.city.example.jp/soshiki/12/345.html</loc></url></urlset>'),
    }
