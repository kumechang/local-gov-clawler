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
        (r"施設を探す|施設から探す|施設検索|[市町村]の施設|みんなの施設", 4),
        (r"体育", 3),
        (r"公共施設|施設案内|施設一覧|施設情報", 3),
        (r"公園", 3),
        (r"文化.?スポーツ|スポーツ.?文化", 2),
    ]
]
# 大分類(先のページを見に行く価値がある。ハブとしては確定しない)。短い文言のときだけ数える。
BROAD_TERMS = re.compile(r"教育(?!委員会)|文化(?!財|祭)|生涯学習|くらし|暮らし|目的から探す|分野から探す|各課のご案内")
BROAD_MAX_LEN = 14
BROAD_WEIGHT = 2
# HTMLサイトマップは1ページでサイト構造が分かるので、リンク先が小さな村でも先の候補を拾える
SITEMAP_PAGE = re.compile(r"サイトマップ|サイト内の?案内")
SITEMAP_WEIGHT = 3

# 「このリンクはお知らせ記事/予約システム/組織名」であることを示す語。
NEGATIVE_TERMS: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"熱中症|指定管理者|募集|令和\d|第\d+回|フェスティバル|開催|中止|休止|臨時|再開|停止|改正|お知らせ|しました|します|ください|イベント|大会|教室|講座|ニュース|結果"), -8, "news_like"),
    (re.compile(r"について|のご案内"), -3, "sentence_like"),
    (re.compile(r"予約|ログイン|申込システム|オンライン"), -5, "reservation_or_login"),
    (re.compile(r"スポーツ(振興|推進)?(課|係|室|協会|団)|体育協会|スポーツ協会"), -2, "organization"),
    (re.compile(r"子育て|保育|幼稚園|こども"), -2, "childcare"),
]
URL_HINTS = re.compile(r"sport|taiiku|undou|gym|shisetsu|park|kouen|ground", re.I)
FACILITY_NAME = re.compile(r"体育館|グラウンド|グランド|運動場|運動公園|野球場|テニスコート|プール|スポーツセンター|多目的広場|武道館|競技場|スポーツ公園|スポーツ広場|サッカー場")
# 施設名リンクの根拠なしでも一覧ページとみなしてよい強い語
STRONG_TEXT = re.compile(r"スポーツ施設|体育施設|運動施設")

MIN_SCORE = 8  # ハブとして確定してよい最低スコア
MARGIN = 4  # 同じ深さの次点との最低差
FETCH_MIN = 2  # 先のページを見に行く最低スコア(大分類を含む)


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
    fetched: bool = False

    def to_dict(self) -> dict:
        return {
            "url": self.url, "text": self.text, "score": self.score, "reasons": self.reasons,
            "region": self.region, "source": self.source, "depth": self.depth,
            "facility_link_count": self.facility_link_count, "page_title": self.page_title,
            "fetched": self.fetched, "viable": is_viable(self),
        }


def score_text(text: str, url: str = "", region: str = "") -> tuple[int, list[str]]:
    t = norm_text(text)
    score, reasons = 0, []
    matched = [(w, p.pattern) for p, w in POSITIVE_TERMS if p.search(t)]
    if matched:
        best = max(matched)
        # 複数語が当たったら最大値+副次の加点(上限つき)
        score += best[0] + min(len(matched) - 1, 2)
        reasons.append(f"text:{best[1]}")
    elif len(t) <= BROAD_MAX_LEN and SITEMAP_PAGE.search(t):
        score += SITEMAP_WEIGHT
        reasons.append("sitemap_page")
    elif len(t) <= BROAD_MAX_LEN and BROAD_TERMS.search(t):
        score += BROAD_WEIGHT
        reasons.append("broad_category")
    if score:
        for p, w, name in NEGATIVE_TERMS:
            if p.search(t):
                score += w
                reasons.append(name)
        if len(t) > 30:
            score -= 3
            reasons.append("long_text")
        if score > 0:
            path = urlsplit(url).path
            if URL_HINTS.search(path):
                score += 2
                reasons.append("url_hint")
            if region in ("nav", "header"):
                score += 1
                reasons.append("region_nav")
        if "news_like" in reasons:
            # お知らせ記事と判定したリンクは、取得対象(FETCH_MIN)にも採用対象にもしない
            score = min(score, FETCH_MIN - 1)
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
    c.fetched = True
    c.facility_link_count = facility_links
    c.page_title = head[:120]
    bonus = min(facility_links, 10)
    if bonus:
        c.score += bonus
        c.reasons.append(f"facility_links:{facility_links}")
    if any(p.search(head) for p, _ in POSITIVE_TERMS[:6]):
        c.score += 3
        c.reasons.append("title_match")


def is_viable(c: Candidate) -> bool:
    """ハブとして採用してよいか。ページを見た候補は、施設名リンクがある(または強い語の見出し)ことが条件。
    施設リンクのない「観光・文化・スポーツ」のような大分類は採用しない(先のページで探す)。"""
    if c.score < MIN_SCORE:
        return False
    if not any(r.startswith("text:") for r in c.reasons):
        return False  # 大分類・サイトマップだけが根拠の候補は探索用。確定はしない(その先で探す)
    if not c.fetched:
        return True
    return bool(c.facility_link_count) or bool(STRONG_TEXT.search(norm_text(c.text)))


@dataclass
class HubDecision:
    outcome: str  # hub_selected / hub_multiple / hub_not_found
    selected: Candidate | None
    top: list[Candidate]

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "selected": self.selected.to_dict() if self.selected else None, "top": [c.to_dict() for c in self.top]}


def decide(cands: list[Candidate]) -> HubDecision:
    # 同一URLは「ページを見た候補」→「高スコア」を優先して1件に
    uniq: dict[str, Candidate] = {}
    for c in cands:
        cur = uniq.get(c.url)
        if cur is None or (c.fetched, c.score) > (cur.fetched, cur.score):
            uniq[c.url] = c
    pool = list(uniq.values())
    viable = [c for c in pool if is_viable(c)]
    # 記録用の上位: 採用可能なものを浅い順・高スコア順、その後に残りを高スコア順
    rest = sorted((c for c in pool if c not in viable), key=lambda c: -c.score)
    top = (sorted(viable, key=lambda c: (c.depth, -c.score)) + rest)[:5]
    if not viable:
        return HubDecision("hub_not_found", None, top)
    # 浅い階層(一覧ページ)を優先する。深い階層の個別ページは、浅い採用候補がある間は競合させない
    tier_depth = min(c.depth for c in viable)
    tier = sorted((c for c in viable if c.depth == tier_depth), key=lambda c: -c.score)
    if len(tier) == 1 or tier[0].score - tier[1].score >= MARGIN:
        return HubDecision("hub_selected", tier[0], top)
    return HubDecision("hub_multiple", None, top)
