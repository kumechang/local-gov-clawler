import gzip

from localgov_crawler.fetcher import FetchResult
from localgov_crawler.robots import parse_robots
from localgov_crawler.sitemap import UrlTally, parse_sitemap

URLSET = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://a.jp/sports/x.html</loc><lastmod>2024-01-05</lastmod></url><url><loc>https://a.jp/soshiki/1/2.html</loc></url></urlset>'
INDEX = b'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://a.jp/s1.xml</loc></sitemap></sitemapindex>'


def res(status, body=b"", ct="text/plain"):
    return FetchResult("https://a.jp/robots.txt", status=status, body=body, content_type=ct)


def test_robots_allow_and_disallow():
    info = parse_robots(res(200, b"User-agent: *\nDisallow: /private/\nCrawl-delay: 3\nSitemap: https://a.jp/sm.xml\n"))
    assert info.available and info.crawl_delay == 3.0 and info.sitemaps == ["https://a.jp/sm.xml"]
    assert info.can_fetch("https://a.jp/") and not info.can_fetch("https://a.jp/private/x")
    assert info.disallow_count == 1 and not info.disallow_all


def test_robots_404_means_no_restriction_and_5xx_means_unreachable():
    assert parse_robots(res(404)).can_fetch("https://a.jp/x")
    assert parse_robots(res(403)).can_fetch("https://a.jp/x")  # RFC 9309: 4xxは制限なし
    bad = parse_robots(res(503))
    assert bad.unreachable and not bad.can_fetch("https://a.jp/x")
    assert parse_robots(FetchResult("u", error_class="timeout")).unreachable


def test_robots_disallow_all():
    assert parse_robots(res(200, b"User-agent: *\nDisallow: /\n")).disallow_all


def test_parse_urlset_index_gzip_and_invalid():
    assert parse_sitemap(URLSET).kind == "urlset" and len(parse_sitemap(URLSET).entries) == 2
    assert parse_sitemap(INDEX).kind == "index"
    assert parse_sitemap(gzip.compress(URLSET)).kind == "urlset"
    assert parse_sitemap(b"<html><body>not found</body></html>").kind == "invalid"
    assert parse_sitemap(b"garbage").kind == "invalid"


def test_tally():
    import re
    t = UrlTally()
    t.add(parse_sitemap(URLSET).entries, re.compile("sports"))
    d = t.to_dict()
    assert d["url_count"] == 2 and d["lastmod_count"] == 1 and d["lastmod_years"] == {"2024": 1}
    assert d["top_level_paths"] == {"/sports": 1, "/soshiki": 1}
    assert d["numeric_id_url_ratio"] == 0.5 and d["keyword_urls"] == ["https://a.jp/sports/x.html"]
