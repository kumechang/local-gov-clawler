"""ジャンル別の入口(ハブ)ページ候補のスコアリング。ルールで決まるものはプログラム、迷うものだけ後段のAIへ。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

from .nav import Link, norm_text

GENRE = "sports_facility"

# 「グラウンド」は常に運動場。「グランド」は、ゴルフ・語尾・区切り・施設語・「の」の前だけ運動場とみなす
# (「三国グランドビジョン」「グランドホテル」などを除くため)
GROUND = r"グラウンド|グランド(?=ゴルフ|$|[・\s、/（(]|施設|一覧|案内|情報|使用|利用|の)"

# (パターン, 重み)。リンク文言はNFKC正規化後に照合する。
POSITIVE_TERMS: list[tuple[re.Pattern, int]] = [
    (re.compile(p), w)
    for p, w in [
        (r"スポーツ施設", 10),
        (r"体育施設", 10),
        (r"運動施設", 9),
        (r"体育館", 6),
        (r"運動公園|総合運動", 6),
        (rf"{GROUND}|運動場", 6),
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
# ラベルの種類(専用性)。複合ラベル(観光・文化・スポーツ など)は大分類で、ハブにはしない。
SPORTS_WORD = re.compile(rf"スポーツ|体育|運動|{GROUND}")
OTHER_TOPICS = re.compile(r"観光|文化(?!財)|生涯学習|公民館|レジャー|健康|教育|福祉|イベント|歴史|芸術|図書館|子育て|保育|学校")
PURE_REMOVE = re.compile(r"スポーツ施設|体育施設|運動施設|スポーツ|体育|運動|レクリエーション|施設|一覧|案内|情報|の|[・/／\s、,&＆と]")
GENERIC_FACILITY = re.compile(r"公共施設|施設案内|施設一覧|施設情報|施設を探す|施設から探す|施設検索|[市町村]の施設|みんなの施設|公園")
PURE_BONUS = 4

# 「利用申請について」のような手続き案内ページは、施設が並んでいても一覧ページではない
PROCEDURE = re.compile(r"申請|届出|手続|申込|様式|ダウンロード")
PROCEDURE_PENALTY = 5

# 施設の一覧ではない専用ラベル(整備事業・学校体育施設の開放制度・予約システムの案内)は、候補には残すが自動確定しない(D-067)。
# 段階1の疑わしい確定: 岡崎市「…整備事業」・堺市「スポーツ施設の整備」・常滑市/あま市「学校体育施設開放…」・東大阪市「OPAS(…システム)」
RESERVATION_TITLE = re.compile(r"予約|申込")
NOT_LISTING = re.compile(r"整備|建て?替|改修|耐震|開放|システム")

# 施設名リンクとして数えないリンク文言: お知らせ記事・工事・入札・休館などの題名(安堵町: 体育館の雨漏修繕工事、広場開放のお知らせ)
# 施設名として数えるときの、リンク/項目の文言の扱い(D-058, D-072 → v10 の D-079 で人間の基準に合わせて変更)
# 強いお知らせ語(工事・入札・休館・募集・開催…)を含むものは、数えない。
# 弱いお知らせ語(ご利用・について・設置・整備・助成…)を含むものは、数える。ただし同じ施設への言及は1件にし、
# 数える件数がこれに頼る(きれいな施設名が MIN_FACILITY_LINKS 件に満たない)ときは SOFT_MIN_FACILITIES 件以上を求める
STRONG_NEWS = re.compile(r"お知らせ|工事|修繕|入札|休館|閉館|利用停止|延期|令和\d|第\d+回|募集|開催|結果|イベント|大会|中止|休止|臨時|再開|停止")
SOFT_NOISE = re.compile(r"ご利用|について|設置|空調|講習|講座|教室|皆さん|皆様|皆さま|お願い|ください|整備|助成|のです|ですか|でしょうか|ますか|開場")
SOFT_MIN_FACILITIES = 3
FACILITY_LINK_MAX_LEN = 30  # きれいな施設名の最大文字数
FACILITY_SOFT_MAX_LEN = 40  # 弱いお知らせ語を含む文言の最大文字数

URL_HINTS = re.compile(r"sport|taiiku|undou|gym|shisetsu|park|kouen|ground", re.I)
FACILITY_NAME = re.compile(
    rf"体育館|{GROUND}|運動場|運動広場|運動公園|野球場|庭球場|テニスコート|テニス場|プール|スポーツセンター|体育センター|多目的広場|武道館|武道場|柔道場|剣道場|弓道場|"
    r"競技場|球技場|スポーツ公園|スポーツ広場|スポーツパーク|スケボーパーク|スケートパーク|スケート場|サッカー場|フットサル場|ゲートボール場|ゴルフ場|アリーナ|海洋センター"
)
# 施設名リンクの根拠なしでも一覧ページとみなしてよい強い語
STRONG_TEXT = re.compile(r"スポーツ施設|体育施設|運動施設")

MIN_SCORE = 8  # ハブとして確定してよい最低スコア
MIN_FACILITY_LINKS = 2  # 一覧ページとみなす施設名リンクの最小数(1件だけのページは一段上のカテゴリであることが多い)
MARGIN = 4  # 同じ深さの次点との最低差
FETCH_MIN = 2  # 先のページを見に行く最低スコア(大分類を含む)


def classify_label(text: str) -> str:
    """sports_pure(スポーツ・体育 など) / sports_composite(観光・文化・スポーツ など) / sports_other(施設名など)
    / generic(公共施設・施設一覧 など) / broad(教育・くらし など) / other"""
    t = norm_text(text)
    if SPORTS_WORD.search(t):
        if OTHER_TOPICS.search(t):
            return "sports_composite"
        return "sports_other" if PURE_REMOVE.sub("", t) else "sports_pure"
    if GENERIC_FACILITY.search(t):
        return "generic"
    if BROAD_TERMS.search(t) or SITEMAP_PAGE.search(t):
        return "broad"
    return "other"


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
    kind: str = "other"
    facility_samples: list[str] = field(default_factory=list)  # 施設名リンクとして数えたリンク文言の例(診断用)
    body_terms: dict[str, int] | None = None  # リンクでない本文中の施設語の出現数(診断用。判定には使わない、D-068)
    link_samples: list[str] | None = None  # 施設名リンクが少ない専用候補ページの、ページ内リンク文言の先頭15件(診断用、D-073)
    breadcrumb: list[list[str]] | None = None  # パンくずリスト [[文言, URL], ...](診断用、D-073)

    def to_dict(self) -> dict:
        return {
            "url": self.url, "text": self.text, "score": self.score, "reasons": self.reasons,
            "region": self.region, "source": self.source, "depth": self.depth,
            "facility_link_count": self.facility_link_count, "page_title": self.page_title,
            "fetched": self.fetched, "kind": self.kind, "facility_samples": self.facility_samples, "body_terms": self.body_terms, "link_samples": self.link_samples, "breadcrumb": self.breadcrumb, "viable": is_viable(self),
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
        kind = classify_label(t)
        if kind.startswith("sports") and PROCEDURE.search(t):
            score -= PROCEDURE_PENALTY
            reasons.append("procedure_page")
        if kind == "sports_pure":
            score += PURE_BONUS
            reasons.append("sports_pure")
        elif kind == "sports_composite":
            # 複合ラベルは先のページを探索する価値はあるが、ハブとしては採用しない(is_viable)。点数は下げない
            reasons.append("composite")
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
            s -= depth - 1
        c = Candidate(l.url, l.text, s, reasons, l.region, source, depth, kind=classify_label(l.text))
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


_LEADING_TAG = re.compile(r"^[【\[（(][^】\])）]*[】\])）]\s*")


def facility_head(text: str) -> str | None:
    """施設の名前(先頭の【…】を除き、最後の施設語までの部分)。同じ施設への言及をまとめるために使う。
    「市民総合体育館空調設備設置(…)」と「市民総合体育館トレーニング講習会」は、どちらも「市民総合体育館」。"""
    t = _LEADING_TAG.sub("", norm_text(text))
    last = None
    for m in FACILITY_NAME.finditer(t):
        last = m
    return re.sub(r"\s+", "", t[: last.end()]) if last else None


def page_features(soup: BeautifulSoup, links: list[Link]) -> tuple[int, str, list[str]]:
    """入口候補ページの特徴: 施設の数、title/h1、数えたものの例。

    人間の判断基準(D-075, D-076)に合わせて、(1) リンクだけでなく、リスト/表の項目(li・dt・dd・td・th)の文字も数え、
    (2) イベントなどの情報が混ざっていても、運動施設が並んでいれば数える。同じ施設への言及は1件にする。
    - 数える: 施設語を含むリンク/項目。強いお知らせ語(工事・入札・休館 等)を含むものは数えない
    - きれいな施設名が MIN_FACILITY_LINKS 件未満なら、弱いお知らせ語を含むものも数えて SOFT_MIN_FACILITIES 件以上のときだけ採る"""
    clean: dict[str, tuple[str, str]] = {}
    soft: dict[str, tuple[str, str]] = {}
    seen_url: set[str] = set()

    def add(text: str, region: str, url: str | None) -> None:
        t = norm_text(text)
        if not t or not FACILITY_NAME.search(t) or STRONG_NEWS.search(t):
            return
        is_soft = bool(SOFT_NOISE.search(t))
        if len(t) > (FACILITY_SOFT_MAX_LEN if is_soft else FACILITY_LINK_MAX_LEN):
            return
        if url is not None:
            if url in seen_url:
                return
            seen_url.add(url)
        key = facility_head(t)
        if not key or key in clean:
            return
        if key in soft:
            if is_soft:
                return
            del soft[key]  # きれいな名前のリンクがあれば、そちらを採る
        (soft if is_soft else clean)[key] = (key, region)

    for l in links:
        if l.same_site:
            add(l.text, l.region, l.url)
    for el in soup.find_all(["li", "dt", "dd", "td", "th"]):
        if el.find(["li", "dt", "dd", "td", "th", "tr", "ul", "ol", "table", "dl"]) is not None:
            continue  # 入れ子の外側は数えない
        add(el.get_text(" "), "text", None)
    total = {**soft, **clean}
    if len(clean) >= MIN_FACILITY_LINKS or len(total) >= SOFT_MIN_FACILITIES:
        facility = list(total.values())
    else:
        facility = list(clean.values())
    n = len(facility)
    samples = [f"{name[:24]}[{region}]" for name, region in facility[:5]]
    title = norm_text(soup.title.get_text()) if soup.title else ""
    h1 = soup.find("h1")
    head = " ".join(filter(None, [title, norm_text(h1.get_text()) if h1 else ""]))
    return n, head, samples


def link_samples(links: list[Link], limit: int = 15) -> list[str]:
    """診断: ページ内リンクの文言の先頭(本文領域を優先)。施設名リンクが少ないページで、何が並んでいるかを見る。"""
    same = [l for l in links if l.same_site]
    pool = [l for l in same if l.region not in ("nav", "header", "footer")] or same
    out, seen = [], set()
    for l in pool:
        t = norm_text(l.text)
        if t in seen:
            continue
        seen.add(t)
        out.append(f"{t[:30]}[{l.region}]")
        if len(out) >= limit:
            break
    return out


_CRUMB_HINT = re.compile(r"breadcrumb|pankuzu|topicpath|topic-path|topic_path|crumb|パンくず", re.I)


def breadcrumb(soup: BeautifulSoup, page_url: str) -> list[list[str]]:
    """パンくずリスト(文言とURL)。見つからなければ空。診断・親ページの特定に使う。"""
    best: list[list[str]] = []
    for el in soup.find_all(True):
        ident = " ".join(filter(None, [el.get("id", ""), " ".join(el.get("class", [])), el.get("aria-label", ""), el.get("itemtype", "")]))
        if not (ident and _CRUMB_HINT.search(ident)):
            continue
        items, seen = [], set()
        for a in el.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
                continue
            url = urldefrag(urljoin(page_url, href))[0]
            text = norm_text(a.get_text(" "))
            if not text or url in seen:
                continue
            seen.add(url)
            items.append([text, url])
        if len(items) >= 2:
            return items
        if items and not best:
            best = items
    return best


def parent_url_candidates(page_url: str, crumbs: list[list[str]]) -> tuple[str, str]:
    """確定ページの1つ上の階層のURLと、その根拠(breadcrumb / url / none)。
    パンくずの最後のリンクが自分自身なら1つ手前、トップページしか無いときは none。URLからの推定は、ファイル名を落とした
    ディレクトリ(index.html なら1つ上のディレクトリ)。"""
    here = _plain(page_url)
    for text, url in reversed(crumbs):
        if _plain(url) != here:
            if urlsplit(url).path.strip("/") == "":
                break  # トップページだけ
            return url, "breadcrumb"
    parts = urlsplit(page_url)
    if parts.query:
        return "", "none"
    segs = [x for x in parts.path.split("/") if x]
    if parts.path.endswith("/"):
        segs = segs[:-1]  # /a/b/ → /a/
    elif segs and segs[-1].lower().startswith("index."):
        segs = segs[:-2]  # /a/b/index.html → /a/
    else:
        segs = segs[:-1]  # /a/b/c.html → /a/b/(そのファイルがあるディレクトリ)
    if not segs:
        return "", "none"
    return f"{parts.scheme}://{parts.netloc}/" + "/".join(segs) + "/", "url"


def _plain(u: str) -> str:
    p = urlsplit(urldefrag(u)[0])
    return f"{p.netloc.lower()}{p.path.rstrip('/')}?{p.query}"


def body_facility_terms(soup: BeautifulSoup) -> dict[str, int]:
    """リンク(aタグ)の外にある本文中の施設語(体育館・テニスコート・プール 等)の出現数。
    施設名がリンクでなく文字・表で並ぶ一覧ページを見分けるための診断(判定には使わない、D-068)。"""
    parts = []
    for node in soup.find_all(string=True):
        if node.parent is None or node.parent.name in ("script", "style", "noscript", "title"):
            continue
        if node.find_parent("a") is not None:
            continue
        parts.append(str(node))
    counts: dict[str, int] = {}
    for m in FACILITY_NAME.finditer(norm_text(" ".join(parts))):
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8])


def rescore_with_page(c: Candidate, facility_links: int, head: str, samples: list[str] | None = None) -> None:
    c.fetched = True
    c.facility_samples = samples or []
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
    """ハブとして自動確定してよいか。ページを取得して施設名リンクを確認できたものだけ。
    - 専用ラベル(スポーツ・体育 など、施設名のラベルも): 施設名リンク2件以上(「一覧」は複数の施設が並ぶページ)
    - 複合ラベル(文化・スポーツ施設 など): 強い語(スポーツ施設等)を含み、施設名リンク3件以上
    - 汎用ラベル(公共施設一覧 など): 施設名リンク3件以上(専用ページが無い自治体向け。品質は generic)
    大分類・サイトマップ・お知らせ記事などは対象外。"""
    if c.score < MIN_SCORE or not c.fetched:
        return False
    if c.kind.startswith("sports") and NOT_LISTING.search(norm_text(c.text)):
        return False
    if c.kind == "generic" and RESERVATION_TITLE.search(c.page_title):
        return False  # 「公共施設予約(…)」のような予約の案内ページは、汎用の施設一覧として確定しない(東大阪市型、D-072)
    fl = c.facility_link_count or 0
    if c.kind in ("sports_pure", "sports_other"):
        return fl >= MIN_FACILITY_LINKS
    if c.kind == "sports_composite":
        return fl >= 3 and bool(STRONG_TEXT.search(norm_text(c.text)))
    if c.kind == "generic":
        return fl >= 3
    return False


@dataclass
class HubDecision:
    outcome: str  # hub_selected / hub_multiple / hub_not_found
    selected: Candidate | None
    top: list[Candidate]
    quality: str = ""  # specific(スポーツ専用/小分類) / generic(公共施設一覧)

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "selected": self.selected.to_dict() if self.selected else None, "top": [c.to_dict() for c in self.top], "quality": self.quality}


def decide(cands: list[Candidate]) -> HubDecision:
    """精度優先: 迷うときは確定せず hub_multiple(後段のAI/手動へ)にする。
    確定の候補は専用ラベル(sports_*)を優先し、その中で浅い(トップに近い)ものを選ぶ。
    複合ラベルの大分類は確定しない。浅い候補と僅差で並ぶものがあれば hub_multiple。"""
    uniq: dict[str, Candidate] = {}
    for c in cands:
        cur = uniq.get(c.url)
        if cur is None or (c.fetched, c.score) > (cur.fetched, cur.score):
            uniq[c.url] = c
    pool = list(uniq.values())
    viable = [c for c in pool if is_viable(c)]
    specific = [c for c in viable if c.kind.startswith("sports")]
    # 強いラベル(スポーツ施設/体育施設/運動施設)があれば、弱いラベル(スポーツ だけ等)より先に評価する。
    # 同じ強さの中では、浅い(トップに近い)ものを選ぶ
    strong = [c for c in specific if STRONG_TEXT.search(norm_text(c.text))]
    specific = sorted(strong or specific, key=lambda c: (c.depth, -c.score))
    generic = sorted((c for c in viable if c.kind == "generic"), key=lambda c: (c.depth, -c.score))
    # 専用ラベルで有望だが、ページを確認できていない候補(深さ3など)
    promising = sorted((c for c in pool if not c.fetched and c.kind.startswith("sports") and c.score >= MIN_SCORE), key=lambda c: -c.score)
    ordered = specific + sorted((c for c in viable if c.kind.startswith("sports") and c not in specific), key=lambda c: (c.depth, -c.score)) + generic + promising + sorted(pool, key=lambda c: -c.score)
    seen: set[str] = set()
    top = [c for c in ordered if not (c.url in seen or seen.add(c.url))][:5]

    tier, quality = (specific, "specific") if specific else (generic, "generic")
    if tier:
        best = tier[0]
        rivals = [c for c in tier[1:] if c.depth == best.depth and best.score - c.score < MARGIN]
        if rivals:
            return HubDecision("hub_multiple", None, top, quality)
        return HubDecision("hub_selected", best, top, quality)
    if promising:
        return HubDecision("hub_multiple", None, top)
    return HubDecision("hub_not_found", None, top)


_TITLE_SPLIT = re.compile(r"\s*[|｜]\s*|\s+[-–—]\s+|/")


def ascend(decision: HubDecision, parent_check: dict | None) -> HubDecision:
    """規則R(D-078): 確定した(または1位の)ページが sports_other(施設の種別名・システム名など)で、
    その1つ上の階層の題名が専用ラベル(スポーツ・スポーツ施設 等)かつ施設が2件以上並ぶなら、親ページを採る。
    例: 常滑市「体育館」の1つ上=「施設案内 スポーツ」、東大阪市「OPAS」の1つ上=「スポーツ」。
    確定ページが専用ラベル(sports_pure)のときは対象外(あわら市は、ユーザーが正しいと判断した確定ページ)。"""
    pc = parent_check
    if not pc or not pc.get("fetched"):
        return decision
    target = decision.selected or next((c for c in decision.top if c.fetched and c.kind.startswith("sports")), None)
    if target is None or target.kind != "sports_other" or pc.get("of") != target.url:
        return decision
    label = _TITLE_SPLIT.split(pc.get("page_title", ""))[0].strip()
    if not label or classify_label(label) != "sports_pure" or NOT_LISTING.search(label) or STRONG_NEWS.search(label):
        return decision
    if (pc.get("facility_link_count") or 0) < MIN_FACILITY_LINKS:
        return decision
    parent = Candidate(
        url=pc.get("final_url") or pc["parent_url"], text=label, score=target.score, reasons=["ascended_from_child", "sports_pure"],
        source="parent", depth=max(1, target.depth - 1), facility_link_count=pc["facility_link_count"], page_title=pc.get("page_title", ""),
        fetched=True, kind="sports_pure", facility_samples=pc.get("facility_samples", []), body_terms=pc.get("body_terms"),
    )
    top = [parent] + [c for c in decision.top if c.url != parent.url][:4]
    return HubDecision("hub_selected", parent, top, "specific")
