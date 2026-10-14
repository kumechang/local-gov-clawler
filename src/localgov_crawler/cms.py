"""CMS推定。シグネチャ照合のみ(ルールベース)。ベンダー名が確定しないURL形式は 'url_pattern:*' として記録する。

ファミリー名は「同じ仕組みだろう」という分類で、ベンダー特定ではない。ベンダー名の対応付けは手動確認の後に足す。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Signature:
    family: str
    source: str  # generator / html / url
    pattern: re.Pattern
    weight: int


def _sig(family: str, source: str, pattern: str, weight: int) -> Signature:
    return Signature(family, source, re.compile(pattern, re.I), weight)


# 実サイトで追加・修正していく。ベンダー名のない 'url_pattern:*' は形式のみの分類。
SIGNATURES: list[Signature] = [
    _sig("wordpress", "generator", r"wordpress", 10),
    _sig("wordpress", "html", r"/wp-content/|/wp-includes/", 6),
    _sig("movabletype", "generator", r"movable\s*type", 10),
    _sig("movabletype", "html", r"/mt-static/", 6),
    _sig("netcommons", "generator", r"netcommons", 10),
    _sig("netcommons", "html", r"/NetCommons/|nc3-", 4),
    _sig("joomla", "generator", r"joomla", 10),
    _sig("drupal", "generator", r"drupal", 10),
    _sig("joruri", "generator", r"joruri", 10),
    _sig("joruri", "html", r"joruri", 4),
    _sig("sitecore", "generator", r"sitecore", 10),
    _sig("url_pattern:soshiki_numeric", "url", r"/soshiki/\d+(/\d+)?\.html", 5),
    _sig("url_pattern:site_numeric", "url", r"/site/[\w\-]+/\d+\.html", 5),
    _sig("url_pattern:kiji_numeric", "url", r"/kiji\d+/", 5),
    _sig("url_pattern:www_contents", "url", r"/www/contents/\d+\.html", 5),
    _sig("url_pattern:cmsfiles", "url", r"/cmsfiles/|/_files/", 3),
    # 奈良県パイロットで共通して見えた形式(ベンダー名は未確定)
    _sig("url_pattern:category_numeric", "url", r"/category/\d+(-\d+){5,}\.html", 6),
    _sig("url_pattern:category_numeric", "url", r"/\d{10}\.html", 4),
    _sig("url_pattern:category_numeric", "url", r"/module/banner\.cgi|/cmsform/", 3),
    _sig("url_pattern:life_numeric", "url", r"/life/\d+(/\d+)+/?$", 6),
    _sig("url_pattern:genre_dir_index", "url", r"/(kanko_bunka_sports|kosodate_manabi|kyoiku_bunka_shogai|kenko_sports|kurashi|shisei)/([\w\-]+/)*(index|\d+)\.html", 5),
    _sig("url_pattern:php_query", "url", r"/(contents_detail|category_list|soshiki_view)\.php", 6),
    _sig("url_pattern:news_event_numeric", "url", r"/(oshirase_top|event_top|event_news|info|event|bosyu|bosyuinfo|daiji)/\d+\.html", 4),
    _sig("url_pattern:soshiki_named", "url", r"/soshiki/[a-z0-9_\-]+(/[a-z0-9_\-]+)+/\d+(/\d+)?\.html", 5),
]


@dataclass
class CmsGuess:
    family: str = "unknown"
    confidence: str = "none"  # high / medium / low / none
    evidence: list[str] = field(default_factory=list)
    all_scores: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"family": self.family, "confidence": self.confidence, "evidence": self.evidence, "scores": self.all_scores, "provenance": "auto"}


def detect_cms(html: str, soup: BeautifulSoup, urls: list[str]) -> CmsGuess:
    generators = [m.get("content", "") for m in soup.find_all("meta", attrs={"name": re.compile("^generator$", re.I)})]
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}

    def hit(sig: Signature, what: str) -> None:
        scores[sig.family] = scores.get(sig.family, 0) + sig.weight
        evidence.setdefault(sig.family, []).append(f"{sig.source}:{what[:80]}")

    for sig in SIGNATURES:
        if sig.source == "generator":
            for g in generators:
                if sig.pattern.search(g):
                    hit(sig, g)
        elif sig.source == "html":
            m = sig.pattern.search(html)
            if m:
                hit(sig, m.group(0))
        elif sig.source == "url":
            matched = [u for u in urls if sig.pattern.search(u)]
            if matched:
                # URL形式は件数が多いほど確からしい(上限つき)
                scores[sig.family] = scores.get(sig.family, 0) + sig.weight + min(len(matched), 5)
                evidence.setdefault(sig.family, []).append(f"url:{len(matched)}件 例 {matched[0][:80]}")
    if not scores:
        return CmsGuess(evidence=[f"generator:{g[:80]}" for g in generators])
    best = max(scores, key=lambda k: scores[k])
    s = scores[best]
    conf = "high" if s >= 10 else "medium" if s >= 6 else "low"
    return CmsGuess(best, conf, evidence[best], scores)
