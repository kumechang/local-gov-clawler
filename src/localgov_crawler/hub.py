"""ジャンル別の入口(ハブ)ページ候補のスコアリング。ルールで決まるものはプログラム、迷うものだけ後段のAIへ。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .nav import Link, norm_text

GENRE = "sports_facility"

# (パターン, 重み)。リンク文言はNFKC正規化後に照合する。
POSITIVE_TERMS: list[tuple[re.Pattern, int]] = [
    (re.compile(p), w)
    for p, w in [
        (r"スポーツ施設", 10),
        (r"体育施設", 10),
        (r"運動施設", 9),
        (r"体育館", 6),
        (r"運動公園|総合運動", 6),
        (r"グラウンド|グランド|運動場", 6),
        (r"スポーツ", 4),
        (r"体育", 3),
        (r"公共施設|施設案内|施設一覧|施設情報", 3),
        (r"公園", 3),
        (r"文化.?スポーツ|スポーツ.?文化", 2),
    ]
]
NEGATIVE_TERMS: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"大会|イベント|教室|講座|募集|お知らせ|ニュース|結果|開催"), -4, "event_or_news"),
    (re.compile(r"予約|ログイン|申込システム|オンライン"), -5, "reservation_or_login"),
    (re.compile(r"スポーツ(振興|推進)?(課|係|室|協会|団)"), -2, "organization"),
]
URL_HINTS = re.compile(r"sport|taiiku|undou|gym|shisetsu|park|kouen|ground", re.I)
FACILITY_NAME = re.compile(r"体育館|グラウンド|グランド|運動場|運動公園|野球場|テニスコート|プール|スポーツセンター|多目的広場|武道館|競技場|スポーツ公園|スポーツ広場|サッカー場")

MIN_SCORE = 8
MARGIN = 4


@dataclass
class Candidate:
    url: str
    text: str
    score: int
    reasons: list[str] = field(default_factory=list)
    region: str = ""
    source: str = "nav"  # nav / depth1_link / sitemap
    depth: int = 1
    facility_link_count: int | None = None
    page_title: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url, "text": self.text, "score": self.score, "reasons": self.reasons,
            "region": self.region, "source": self.source, "depth": self.depth,
            "facility_link_count": self.facility_link_count, "page_title": self.page_title,
        }


def score_text(text: str, url: str = "", region: str = "") -> tuple[int, list[str]]:
    t = norm_text(text)
    score, reasons = 0, []
    best_pos = max(((w, p.pattern) for p, w in POSITIVE_TERMS if p.search(t)), default=None)
    if best_pos:
        # 複数語が当たったら最大値+副次の加点(上限つき)
        extra = sum(1 for p, _ in POSITIVE_TERMS if p.search(t)) - 1
        score += best_pos[0] + min(extra, 2)
        reasons.append(f"text:{best_pos[1]}")
    if score:
        for p, w, name in NEGATIVE_TERMS:
            if p.search(t):
                score += w
                reasons.append(name)
        if len(t) > 40:
            score -= 3
            reasons.append("long_text")
        path = urlsplit(url).path
        if URL_HINTS.search(path):
            score += 2
            reasons.append("url_hint")
        if region in ("nav", "header"):
            score += 1
            reasons.append("region_nav")
    return score, reasons


def candidates_from_links(links: list[Link], source: str, depth: int) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for l in links:
        if not l.same_site or l.is_pdf:
            continue
        s, reasons = score_text(l.text, l.url, l.region)
        if s <= 0:
            continue
        if depth > 1:
            s -= 1
        c = Candidate(l.url, l.text, s, reasons, l.region, source, depth)
        if l.url not in best or c.score > best[l.url].score:
            best[l.url] = c
    return sorted(best.values(), key=lambda c: -c.score)


def candidates_from_urls(urls: list[str]) -> list[Candidate]:
    """サイトマップのURLのうちパスにジャンル語が含まれるもの(URLが意味を持つCMSのみ有効)。"""
    out = []
    for u in urls:
        if URL_HINTS.search(urlsplit(u).path):
            out.append(Candidate(u, "", 2, ["sitemap_url_hint"], "", "sitemap", 1))
    return out


def page_features(soup: BeautifulSoup, links: list[Link]) -> tuple[int, str]:
    """入口候補ページの特徴: 施設名らしいリンクの数と、title/h1。"""
    n = sum(1 for l in links if l.same_site and FACILITY_NAME.search(norm_text(l.text)))
    title = norm_text(soup.title.get_text()) if soup.title else ""
    h1 = soup.find("h1")
    head = " ".join(filter(None, [title, norm_text(h1.get_text()) if h1 else ""]))
    return n, head


def rescore_with_page(c: Candidate, facility_links: int, head: str) -> None:
    c.facility_link_count = facility_links
    c.page_title = head[:120]
    bonus = min(facility_links, 10)
    if bonus:
        c.score += bonus
        c.reasons.append(f"facility_links:{facility_links}")
    if any(p.search(head) for p, _ in POSITIVE_TERMS[:6]):
        c.score += 3
        c.reasons.append("title_match")


@dataclass
class HubDecision:
    outcome: str  # hub_selected / hub_multiple / hub_not_found
    selected: Candidate | None
    top: list[Candidate]

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "selected": self.selected.to_dict() if self.selected else None, "top": [c.to_dict() for c in self.top]}


def decide(cands: list[Candidate]) -> HubDecision:
    # 同一URLは最高スコアのみ
    uniq: dict[str, Candidate] = {}
    for c in cands:
        if c.url not in uniq or c.score > uniq[c.url].score:
            uniq[c.url] = c
    ranked = sorted(uniq.values(), key=lambda c: -c.score)
    top = ranked[:5]
    viable = [c for c in ranked if c.score >= MIN_SCORE]
    if not viable:
        return HubDecision("hub_not_found", None, top)
    if len(viable) == 1 or viable[0].score - viable[1].score >= MARGIN:
        return HubDecision("hub_selected", viable[0], top)
    return HubDecision("hub_multiple", None, top)
