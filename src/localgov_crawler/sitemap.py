"""XMLサイトマップのパースと集計。URL全件は保存せず、要約と少量のサンプルだけ残す。"""
from __future__ import annotations

import gzip
import re
import zlib
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from lxml import etree

MAX_DECOMPRESSED = 50_000_000
_NUMERIC_PATH = re.compile(r"/\d{2,}(\.html?)?$|/\d+/\d+\.html?$")


@dataclass
class ParsedSitemap:
    kind: str  # urlset / index / invalid
    entries: list[tuple[str, str]] = field(default_factory=list)  # (loc, lastmod)


def maybe_decompress(body: bytes) -> bytes:
    if body[:2] != b"\x1f\x8b":
        return body
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(body, MAX_DECOMPRESSED)
    return out


def parse_sitemap(body: bytes) -> ParsedSitemap:
    try:
        body = maybe_decompress(body)
    except (zlib.error, OSError, EOFError):
        return ParsedSitemap("invalid")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=False)
    try:
        root = etree.fromstring(body, parser)
    except etree.XMLSyntaxError:
        return ParsedSitemap("invalid")
    if root is None:
        return ParsedSitemap("invalid")
    name = etree.QName(root).localname
    if name not in ("urlset", "sitemapindex"):
        return ParsedSitemap("invalid")
    child = "url" if name == "urlset" else "sitemap"
    entries = []
    for el in root:
        if not isinstance(el.tag, str) or etree.QName(el).localname != child:
            continue
        loc = lastmod = ""
        for sub in el:
            if not isinstance(sub.tag, str):
                continue
            ln = etree.QName(sub).localname
            if ln == "loc":
                loc = (sub.text or "").strip()
            elif ln == "lastmod":
                lastmod = (sub.text or "").strip()
        if loc:
            entries.append((loc, lastmod))
    return ParsedSitemap("urlset" if name == "urlset" else "index", entries)


@dataclass
class UrlTally:
    """複数のサイトマップにまたがってURLを集計する。"""

    total: int = 0
    with_lastmod: int = 0
    lastmod_min: str = ""
    lastmod_max: str = ""
    years: Counter = field(default_factory=Counter)
    top_paths: Counter = field(default_factory=Counter)
    numeric_id_urls: int = 0
    keyword_urls: list[str] = field(default_factory=list)
    sample: list[str] = field(default_factory=list)  # CMS推定用。保存はしない

    def add(self, entries: list[tuple[str, str]], keyword_re: re.Pattern | None = None, keyword_cap: int = 50) -> None:
        for loc, lastmod in entries:
            self.total += 1
            if len(self.sample) < 200:
                self.sample.append(loc)
            path = urlsplit(loc).path or "/"
            seg = path.strip("/").split("/", 1)[0]
            self.top_paths["/" + seg if seg else "/"] += 1
            if _NUMERIC_PATH.search(path):
                self.numeric_id_urls += 1
            if lastmod:
                self.with_lastmod += 1
                d = lastmod[:10]
                if not self.lastmod_min or d < self.lastmod_min:
                    self.lastmod_min = d
                if d > self.lastmod_max:
                    self.lastmod_max = d
                if re.match(r"\d{4}", d):
                    self.years[d[:4]] += 1
            if keyword_re and len(self.keyword_urls) < keyword_cap and keyword_re.search(loc):
                self.keyword_urls.append(loc)

    def to_dict(self) -> dict:
        return {
            "url_count": self.total,
            "lastmod_count": self.with_lastmod,
            "lastmod_min": self.lastmod_min,
            "lastmod_max": self.lastmod_max,
            "lastmod_years": dict(sorted(self.years.items())),
            "numeric_id_url_ratio": round(self.numeric_id_urls / self.total, 3) if self.total else 0.0,
            "top_level_paths": dict(self.top_paths.most_common(30)),
            "keyword_urls": self.keyword_urls,
        }
