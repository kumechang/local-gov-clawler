"""ワード調査(D-106/D-107): 一覧・施設詳細・スポーツイベントのページに、特定のワードがあるかを調べる。
ハブの特定(pipeline)の結果を入口にして、そこから同じサイト内の関連ページを浅くたどり、ページごとにワードの有無を記録する。
保存するのは、ワードの有無・出たページのURL・前後の短い文だけ(本文の転載はしない)。"""
from __future__ import annotations

import heapq
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from . import __version__, hub
from .fetcher import Fetcher
from .html import decode_bytes, parse_html
from .municipalities import Municipality
from .nav import base_host, extract_links, is_same_site, norm_text
from .pipeline import Config, _Ctx, _now

SURVEY_SCHEMA = 8

# 予約システム・ログインが必要なページには入らない(handoff §3、CLAUDE.md)
RESERVATION_URL = re.compile(r"yoyaku|reserve|rsv|login|logon|signin|/sp/reserve|shisetsu-?yoyaku|k-?system|eshisetsu|e-?shisetsu", re.I)
RESERVATION_TEXT = re.compile(r"予約|ログイン|申込システム|利用者登録|マイページ")
# スポーツのページとしてたどってよいリンク文言(施設・種目・場所)
FOLLOW_SPORTS = re.compile(
    rf"スポーツ|体育|運動|{hub.GROUND}|公園|広場|コート|プール|体育館|競技場|野球場|テニス|ゴルフ|ゲートボール|武道|柔道|剣道|弓道|アリーナ|センター|施設|レクリエーション|健康|ウォーキング|サッカー|バスケ|バレー|卓球|ソフトボール|マラソン|ランニング"
)
# イベントの入口・イベントのページの文言
EVENT_ENTRANCE = re.compile(r"スポーツ.{0,6}(大会|イベント|教室|行事|スケジュール|カレンダー)|大会|イベント|行事|教室|講座")
EVENT_LINK = re.compile(r"大会|イベント|行事|教室|講座|体験|交流|カップ|選手権|フェスタ|フェスティバル|祭|レクリエーション|ウォーキング|マラソン")
# 個別のお知らせ記事(入口にしない)
SITEMAP_LABEL = re.compile(r"サイトマップ|サイト内の?案内")
NEWS_LABEL = re.compile(r"お知らせ|に関する|令和|第\d+回|募集|結果|開催のお|について")
# ナビ・サイドバー等を表すクラス名・ID(トークンが完全に一致するときだけ。部分一致だと、ページ全体を囲む要素まで消してしまう、D-111)
_CHROME_TOKEN = re.compile(r"(?:g|global|local|main|side|sub|foot|head|top|page)?-?(?:nav|navi|navigation|gnav|menu|sidebar|sidenav|breadcrumbs?|pankuzu|topicpath|footer|header)", re.I)
_MAIN_SELECTORS = ("main", "[role=main]", "#main", "#main_body", "#mainContents", "#contents", "#content", "#maincontent", "article", ".main")
_DROP_TAGS = ("script", "style", "noscript")
_BLOCK_TAGS = ("p", "li", "tr", "td", "th", "dt", "dd", "div", "section", "article", "table", "ul", "ol", "dl", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "figure", "figcaption", "main")
_SEMANTIC_CHROME = ("nav", "header", "footer", "aside")
WRAPPER_RATIO = 0.6  # 本文の6割を超える要素は、ナビでなく全体を囲む要素とみなして消さない


# ページの内容による分類(題名・URLから)。たどった経路で付く role とは別に付ける
ORG_TITLE = re.compile(r"協会|連盟|連合|委員|クラブ|団体|サークル|審議会|表彰|受賞|課の仕事|会長|役員|スポーツ少年団|同好会")
EVENT_STRONG = re.compile(r"大会|イベント|教室|講座|開催|募集|日程|カレンダー|スケジュール|フェスタ|フェスティバル|選手権|カップ|結果")
EVENT_WEAK = re.compile(r"体験|交流|記録|行事")  # 『山村体験宿泊施設』のように施設名にも入る語。施設を表す語があれば施設とみなす(D-116)
FACILITY_TITLE = re.compile(r"施設|公園|運動場|運動広場|広場|体育館|グラウンド|グランド|コート|プール|競技場|野球場|センター|ゴルフ場|ひろば|宿泊")


def classify_page(title: str, url: str = "") -> str:
    """organization(協会・課の紹介など)/ event(大会・教室など)/ facility(施設・場所)/ other。題名で判断する。"""
    t = norm_text(title)
    if ORG_TITLE.search(t):
        return "organization"
    if EVENT_STRONG.search(t):
        return "event"
    facility = bool(FACILITY_TITLE.search(t) or hub.facility_head(t) or re.search(r"shisetsu|sisetu|facility|koen|park|ground", url, re.I))
    if EVENT_WEAK.search(t) and not facility:
        return "event"
    return "facility" if facility else "other"


@dataclass
class KeywordSpec:
    name: str
    label: str
    patterns: list[re.Pattern]

    @classmethod
    def load(cls, path: str | Path) -> "KeywordSpec":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["name"], d.get("label", d["name"]), [re.compile(p) for p in d["patterns"]])

    def find(self, text: str) -> list[re.Match]:
        t = norm_text(text)
        out: list[re.Match] = []
        for p in self.patterns:
            out += list(p.finditer(t))
        return sorted(out, key=lambda m: m.start())

    def in_text(self, text: str) -> bool:
        return bool(self.find(text))

    def find_lines(self, text: str) -> list[tuple[str, re.Match]]:
        """行(改行区切り)ごとの一致。(その行の文, 一致) の組。"""
        out = []
        for raw in text.split("\n"):
            line = norm_text(raw)
            if line:
                out += [(line, m) for m in self.find(line)]
        return out

    def find_affirmative(self, text: str) -> list[tuple[str, re.Match]]:
        """否定の文を除いた一致。ワードと**同じ行**で、直後(同じ文の中)に『いただけません・禁止』などがあるときだけ否定とみなす。
        別の行・別の項目(他のスポーツの禁止など)は無関係(D-116)。"""
        return [(l, m) for l, m in self.find_lines(text) if not is_negated(l, m.end())]


# ワードにかかる否定(D-113、D-119)。『グラウンド・ゴルフではご利用いただけません』のように、ワードの直後に区切りなしで続く否定だけを数える。
# 同じ行でも、読点・中点・空白・括弧などで区切られた先の否定(他のスポーツの『使用禁止』など)や、『グラウンド・ゴルフ以外は…』は、ワードの否定ではない。
NEGATION = re.compile(r"いただけません|できません|できない|使えません|ご遠慮|不可|禁止|対象外|行えません|なれません|お断り")
NEGATION_WINDOW = 40
NEGATION_MAX_GAP = 20
CLAUSE_BREAK = re.compile(r"[、，,;；/／・･()（）「」『』\[\]【】\s]")
EXCEPT_PREFIX = re.compile(r"^(?:以外|を除|除く|のほか|の他|以外の|のみ)")


def is_negated(text: str, end: int) -> bool:
    tail = text[end: end + NEGATION_WINDOW].split("。", 1)[0]
    if EXCEPT_PREFIX.match(tail):
        return False
    m = NEGATION.search(tail)
    if not m:
        return False
    gap = tail[: m.start()]
    return len(gap) <= NEGATION_MAX_GAP and not CLAUSE_BREAK.search(gap)


@dataclass
class SurveyConfig:
    route: str = "local"
    max_pages: int = 200  # 1自治体あたり取得するページ数の上限(サイト全体をたどらないための安全弁。時間ではなく範囲の限定)
    seed_depth: int = 2  # 入口から何階層たどるか(施設詳細・イベントとも)
    max_seeds: int = 12
    max_event_pages: int = 80  # イベントのページ(月次の一覧など)で上限を使い切らないための枠
    snippet_chars: int = 30
    retry_wait: float = 2.0
    max_requests: int = field(default=0)  # 0なら max_pages + 8 にする

    def pipeline_config(self) -> Config:
        return Config(route=self.route, max_requests=self.max_requests or self.max_pages + 8, retry_wait=self.retry_wait)


def _text_len(tag) -> int:
    return len(norm_text(tag.get_text(" ")))


def page_text(soup: BeautifulSoup) -> tuple[str, str]:
    """(題名, 本文)。ナビ・ヘッダー・フッター・サイドバーは本文から外す(全ページ共通のワードを拾わないため)。
    本文の枠(main など)があればその中だけを見る。ページ全体を囲む要素(本文の6割超)は消さない。"""
    title = norm_text(soup.title.get_text(" ")) if soup.title else ""
    h1 = soup.find("h1")
    if h1 and norm_text(h1.get_text(" ")) not in title:
        title = f"{title} {norm_text(h1.get_text(' '))}".strip()
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    base = soup.body or soup
    for sel in _MAIN_SELECTORS:
        found = base.select_one(sel)
        if found is not None and _text_len(found) >= 100:
            base = found
            break
    total = _text_len(base)
    limit = total * WRAPPER_RATIO
    for tag in list(base.find_all(True)):
        if getattr(tag, "decomposed", False) or tag.attrs is None or tag is base:
            continue
        if tag.name in _SEMANTIC_CHROME:
            if tag.find(["main", "article"]) is None:  # 本文を囲んでいるものは消さない
                tag.decompose()
            continue
        tokens = [t for t in (tag.get("class") or []) + [tag.get("id") or ""] if t]
        if any(_CHROME_TOKEN.fullmatch(t.replace("_", "-")) for t in tokens) and _text_len(tag) <= limit:
            tag.decompose()
    # ブロック要素の境目を改行にして、行ごとに見られるようにする(否定の文を同じ行だけで判断するため、D-116)
    for br in base.find_all("br"):
        br.replace_with("\n")
    for tag in base.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = [norm_text(l) for l in base.get_text("").split("\n")]
    return title, "\n".join(l for l in lines if l)


def match_keys(spec: KeywordSpec, text: str, limit: int = 5, affirmative: bool = False) -> list[str]:
    """ワードと、その直後の15文字。全ページ共通の文(ナビ・バナー)を見分ける目印。"""
    pairs = spec.find_affirmative(text) if affirmative else spec.find_lines(text)
    return [line[m.start(): m.end() + 15] for line, m in pairs[:limit]]


def snippets(spec: KeywordSpec, text: str, chars: int = 30, limit: int = 3, affirmative: bool = False) -> list[str]:
    pairs = spec.find_affirmative(text) if affirmative else spec.find_lines(text)
    return [line[max(0, m.start() - chars): m.end() + chars] for line, m in pairs[:limit]]


def seeds_from_result(result: dict, max_seeds: int = 12) -> list[dict]:
    """ハブ判定の結果から、調べ始めるページ(入口)を集める。同点の候補も全部入れる。"""
    seeds: list[dict] = []
    seen: set[str] = set()

    def add(url: str, role: str, source: str, text: str = "") -> None:
        if url and url not in seen and not RESERVATION_URL.search(url):
            seen.add(url)
            seeds.append({"url": url, "role": role, "source": source, "text": text})

    for ge in result.get("genre_entrypoints", []):
        sel = ge.get("selected")
        if sel:
            add(sel["url"], "listing", "selected", sel.get("text", ""))
        for c in ge.get("candidates", []):
            if c.get("kind", "").startswith("sports") or (c.get("kind") == "generic" and c.get("score", 0) >= hub.MIN_SCORE):
                if c.get("score", 0) >= 5 and not hub.NOT_LISTING.search(norm_text(c.get("text", ""))):
                    add(c["url"], "listing", "candidate", c.get("text", ""))
    nav = [l for l in result.get("nav_links", []) if l.get("same_site") and not l.get("is_pdf")]
    for l in nav:
        t = norm_text(l["text"])
        if len(t) <= 24 and hub.SPORTS_WORD.search(t) and not RESERVATION_TEXT.search(t) and not NEWS_LABEL.search(t):
            add(l["url"], "event" if EVENT_ENTRANCE.search(t) else "sports_nav", "nav", t)
    for l in nav:
        t = norm_text(l["text"])
        if len(t) <= 24 and EVENT_ENTRANCE.search(t) and not RESERVATION_TEXT.search(t) and not NEWS_LABEL.search(t):
            add(l["url"], "event", "nav", t)
    order = {"listing": 0, "sports_nav": 1, "event": 2}
    return sorted(seeds, key=lambda s: order[s["role"]])[:max_seeds]


BROAD_NAV = re.compile(r"サイトマップ|サイト内の?案内|文化|生涯学習|学習|教育|くらし|暮らし|生活|施設|市民|町民|村民|観光|イベント|行事|健康|レクリエーション|分野|目的|各課")


def fallback_seeds(links: list[dict], max_seeds: int = 12) -> list[dict]:
    """スポーツの入口が見つからない自治体の入口(D-117)。トップのナビにある『サイトマップ』『文化・生涯学習』『施設』『イベント』などの
    大分類を入口にし、その先でスポーツのリンクを探す(1階層深くたどる)。"""
    cand = []
    for l in links:
        t = norm_text(l.get("text", ""))
        if not l.get("same_site", True) or l.get("is_pdf") or len(t) > 24 or not t:
            continue
        if not (BROAD_NAV.search(t) or hub.SPORTS_WORD.search(t)) or RESERVATION_TEXT.search(t) or NEWS_LABEL.search(t) or RESERVATION_URL.search(l["url"]):
            continue
        if SITEMAP_LABEL.search(t):
            rank = 0
        elif hub.SPORTS_WORD.search(t):
            rank = 1
        elif re.search(r"文化|生涯学習|学習|教育", t):
            rank = 2
        elif re.search(r"施設|イベント|行事", t):
            rank = 3
        else:
            rank = 4
        cand.append((rank, t, l["url"]))
    seeds, seen = [], set()
    for rank, t, url in sorted(cand, key=lambda x: x[0]):
        if url in seen:
            continue
        seen.add(url)
        seeds.append({"url": url, "role": "sports_nav" if hub.SPORTS_WORD.search(t) else "broad", "source": "fallback", "text": t})
    return seeds[:max_seeds]


def _child_role(parent_role: str, text: str, spec: KeywordSpec) -> str | None:
    """リンクをたどるか・たどるならどの役割か。たどらないなら None。"""
    t = norm_text(text)
    if len(t) > 60 or RESERVATION_TEXT.search(t) or hub.STRONG_NEWS.search(t) and not EVENT_LINK.search(t):
        return None
    if parent_role == "broad" and hub.SPORTS_WORD.search(t) and not spec.in_text(t):
        return "sports_nav"  # 入口が見つからない自治体: 大分類のページの中の『スポーツ』への入口(D-117)
    if spec.in_text(t):
        return "facility" if parent_role != "event" else "event"
    if parent_role == "event":
        return "event" if (EVENT_LINK.search(t) or FOLLOW_SPORTS.search(t)) else None
    if EVENT_LINK.search(t) and FOLLOW_SPORTS.search(t):
        return "event"
    if hub.facility_head(t) or FOLLOW_SPORTS.search(t):
        return "facility"
    return None


def _priority(role: str, depth: int, text: str, spec: KeywordSpec) -> tuple[int, int]:
    """小さいほど先に取得する。0=ワードを含むリンク、1=一覧・スポーツの入口・施設名、2=その他のスポーツ関連、3=イベント。"""
    if spec.in_text(text):
        return 0, depth
    if role in ("listing", "sports_nav") or (role == "facility" and hub.facility_head(text)):
        return 1, depth
    if role == "event":
        return 3, depth
    return 2, depth


def survey_municipality(m: Municipality, result: dict | None, fetcher: Fetcher, spec: KeywordSpec, cfg: SurveyConfig) -> dict:
    started = _now()
    out: dict = {
        "schema_version": SURVEY_SCHEMA,
        "keyword": spec.name,
        "municipality": {"code": m.code, "name": m.name, "prefecture": m.prefecture_name, "scope": m.scope, "official_url": m.url},
        "run": {"route": cfg.route, "crawler_version": __version__, "started_at": started, "finished_at": "", "max_pages": cfg.max_pages, "max_event_pages": cfg.max_event_pages, "seed_depth": cfg.seed_depth, "compact": True},
        "outcome": "", "failure_class": "", "found": False, "pdf_link_found": False, "hit_roles": [], "hit_kinds": [], "seeds": [], "pages": [], "nav_hits": [], "pdf_link_hits": [], "requests": [],
    }
    ctx = _Ctx(fetcher, cfg.pipeline_config())
    try:
        _survey(m, result, ctx, spec, cfg, out)
    finally:
        out["requests"] = ctx.log
        out["run"]["finished_at"] = _now()
        out["run"]["request_count"] = len(ctx.log)
        out["found"] = any(p["hit"] for p in out["pages"]) or bool(out["nav_hits"])
        out["pdf_link_found"] = bool(out["pdf_link_hits"])
        out["hit_roles"] = sorted({p["role"] for p in out["pages"] if p["hit"]})
        out["hit_kinds"] = sorted({p.get("kind", "other") for p in out["pages"] if p["hit"]})
    return out


def _survey(m: Municipality, result: dict | None, ctx: _Ctx, spec: KeywordSpec, cfg: SurveyConfig, out: dict) -> None:
    if not m.url or result is None:
        out["outcome"] = "no_url" if not m.url else "no_seed"
        return
    out["nav_hits"] = [{"text": l["text"], "url": l["url"]} for l in result.get("nav_links", []) if spec.in_text(l["text"]) and l.get("same_site")][:20]
    seeds = seeds_from_result(result, cfg.max_seeds)
    out["seed_mode"] = "normal"
    robots = ctx.load_robots(m.url)
    if robots.unreachable:
        out["outcome"], out["failure_class"] = "fetch_failed", "robots_unreachable"
        return
    site_host = base_host(m.url)
    if not seeds:
        # 入口が見つからない自治体(D-117): ナビが取れていない・JS描画なら、トップを取得し直し(JS描画はヘッドレス)、大分類を入口にする
        links = [l for l in result.get("nav_links", []) if l.get("same_site") and not l.get("is_pdf")]
        needs_headless = bool(result.get("site_profile", {}).get("rendering", {}).get("needs_headless"))
        if needs_headless or len(links) < 5:
            top = ctx.get(m.url)
            if top.ok and is_same_site(top.final_url, site_host):
                links = [l.to_dict() for l in extract_links(parse_html(decode_bytes(top.body, top.content_type)), top.final_url, site_host) if l.same_site and not l.is_pdf]
            elif not links:
                out["outcome"], out["failure_class"] = "fetch_failed", f"top_fetch_{top.error_class or 'other'}"
                return
        seeds = fallback_seeds(links, cfg.max_seeds)
        out["seed_mode"] = "fallback"
    out["seeds"] = seeds
    if not seeds:
        out["outcome"] = "no_seed"
        return
    heap: list = []
    seq = 0

    def push(url: str, role: str, depth: int, via: str, text: str, maxd: int) -> None:
        nonlocal seq
        seq += 1
        cls, d = _priority(role, depth, text or via, spec)
        heapq.heappush(heap, (cls, d, seq, url, role, depth, via, maxd))

    queued = {s["url"] for s in seeds}
    for sd in seeds:
        push(sd["url"], sd["role"], 0, "seed", sd.get("text", ""), cfg.seed_depth + (1 if sd["role"] == "broad" or sd.get("source") == "fallback" else 0))
    fetched = 0
    event_pages = 0
    stopped = "exhausted"
    while heap:
        if fetched >= cfg.max_pages:
            stopped = "max_pages"
            break
        _, _, _, url, role, depth, via, maxd = heapq.heappop(heap)
        if role == "event" and event_pages >= cfg.max_event_pages:
            continue
        res = ctx.get(url)
        if res.error_class == "budget_exceeded":
            stopped = "max_requests"
            break
        page = {"url": url, "role": role, "depth": depth, "via": via, "status": res.status, "error_class": res.error_class, "hit": False}
        if not res.ok or (res.content_type and "html" not in res.content_type.lower()):
            out["pages"].append(page)
            continue
        if not is_same_site(res.final_url, site_host):
            page["error_class"] = "offsite_redirect"
            out["pages"].append(page)
            continue
        fetched += 1
        event_pages += role == "event"
        soup = parse_html(decode_bytes(res.body, res.content_type))
        links = extract_links(soup, res.final_url, site_host)
        title, body = page_text(parse_html(decode_bytes(res.body, res.content_type)))
        hits_t, hits_b = spec.find(title), spec.find_affirmative(body)
        all_pairs = spec.find_lines(body)
        negated = len(all_pairs) - len(hits_b)
        affirmed = {(l, m.start()) for l, m in hits_b}
        negated_samples = [l[max(0, m.start() - 20): m.end() + 60] for l, m in all_pairs if (l, m.start()) not in affirmed][:2]
        link_hits = [l for l in links if spec.in_text(l.text) and not l.is_pdf and l.region not in ("nav", "header", "footer")]
        page.update(title=title[:80], kind=classify_page(title, res.final_url), text_len=len(body), hit=bool(hits_t or hits_b or link_hits), count=len(hits_b) + len(hits_t), negated=negated, negated_samples=negated_samples,
                    in_title=bool(hits_t), snippets=snippets(spec, body, cfg.snippet_chars, affirmative=True), keys=match_keys(spec, body, affirmative=True), link_hits=[{"text": l.text[:60], "url": l.url} for l in link_hits[:5]])
        out["pages"].append(page)
        for l in links:
            if l.is_pdf and spec.in_text(l.text) and len(out["pdf_link_hits"]) < 20:
                out["pdf_link_hits"].append({"text": l.text[:80], "url": l.url, "page": url})
        if depth >= maxd:
            continue
        for l in links:
            if not l.same_site or l.is_pdf or l.url in queued or RESERVATION_URL.search(l.url) or l.region in ("footer",):
                continue
            child = _child_role(role, l.text, spec)
            if child is None:
                continue
            queued.add(l.url)
            push(l.url, child, depth + 1, norm_text(l.text)[:40], norm_text(l.text), maxd)
    _drop_boilerplate(out["pages"], fetched)
    out["outcome"] = "surveyed"
    out["stopped"] = stopped
    out["pages_fetched"] = fetched


def _drop_boilerplate(pages: list[dict], fetched: int) -> None:
    """多くのページに同じ文脈で出るワード(ナビの見落とし・全ページ共通のバナー)は、ページの内容ではないので数えない。"""
    from collections import Counter
    threshold = max(3, -(-fetched // 5))  # 取得ページの2割(最低3ページ)
    count: Counter = Counter()
    for p in pages:
        for key in set(p.get("keys", []) + [l["url"] for l in p.get("link_hits", [])]):
            count[key] += 1
    for p in pages:
        keys = p.pop("keys", None) or []
        if not p.get("hit") or p.get("in_title"):
            continue
        keys = keys + [l["url"] for l in p.get("link_hits", [])]
        if keys and all(count[k] >= threshold for k in keys):
            p["hit"], p["boilerplate"] = False, True


def write_survey(root: Path, survey: dict, prefecture_code: str) -> Path:
    path = Path(root) / survey["keyword"] / survey["run"]["route"] / prefecture_code / f"{survey['municipality']['code']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(survey, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_surveys(root: Path, keyword: str, route: str) -> list[dict]:
    base = Path(root) / keyword / route
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("*/*.json"))]


def survey_rows(surveys: list[dict]) -> list[dict]:
    rows = []
    for s in surveys:
        hits = [p for p in s["pages"] if p["hit"]]
        first = hits[0] if hits else None
        rows.append({
            "municipality_code": s["municipality"]["code"], "municipality_name": s["municipality"]["name"], "prefecture": s["municipality"]["prefecture"],
            "outcome": s["outcome"], "found": s["found"], "pdf_link_found": s.get("pdf_link_found", bool(s["pdf_link_hits"])), "hit_pages": len(hits),
            "hit_kinds": "|".join(s.get("hit_kinds", [])), "hit_roles": "|".join(s["hit_roles"]),
            "pages_fetched": s.get("pages_fetched", 0), "stopped": s.get("stopped", ""), "nav_hits": len(s["nav_hits"]), "pdf_link_hits": len(s["pdf_link_hits"]),
            "first_hit_url": first["url"] if first else (s["nav_hits"][0]["url"] if s["nav_hits"] else ""),
            "first_hit_role": first["role"] if first else "", "first_hit_kind": first.get("kind", "") if first else "", "first_hit_title": first.get("title", "") if first else "",
            "first_hit_snippet": (first.get("snippets") or [""])[0] if first else "",
        })
    return rows


def summary_markdown(rows: list[dict], keyword: str) -> str:
    n = len(rows)
    surveyed = [r for r in rows if r["outcome"] == "surveyed"]
    found = [r for r in rows if r["found"]]
    from collections import Counter
    kinds = Counter(k for r in found for k in r.get("hit_kinds", "").split("|") if k)
    pdf_only = [r for r in rows if r["pdf_link_found"] and not r["found"]]
    outcomes = Counter(r["outcome"] for r in rows)
    lines = [f"# ワード調査サマリ (keyword: {keyword})", "", f"- 対象: {n}自治体", f"- 調査できた: {len(surveyed)}", f"- ワードがあった: {len(found)} ({(len(found) / n if n else 0):.1%})",
             "- ワードのあったページの種類(自治体数、題名で判断): " + "、".join(f"{k} {v}" for k, v in sorted(kinds.items())),
             f"- 本文・題名・リンクには無く、PDFのリンク文言だけにあった: {len(pdf_only)}",
             "- 平均取得ページ数: " + (f"{sum(r['pages_fetched'] for r in surveyed) / len(surveyed):.1f}" if surveyed else "-"),
             "- 上限(max_pages)に達した: " + str(sum(1 for r in surveyed if r["stopped"] == "max_pages")), "", "## outcome別", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(outcomes.items())]
    return "\n".join(lines) + "\n"
