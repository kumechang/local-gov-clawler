"""ワード調査で見つかった『イベント』のページから、イベントの名称・開催日・会場・主催・申込・参加費・問い合わせ先を取り出す(D-137)。
ルールだけで取り出す(AIは使わない、D-050)。ページは取得し直す(HTMLは保存していない)。
保存するのは、項目の値と、ワードの前後の短い文だけ(本文の転載はしない)。"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from . import __version__
from .extract import _inquiry, _kv_pairs, find_phones
from .fetcher import Fetcher
from .html import decode_bytes, parse_html
from .municipalities import Municipality
from .nav import base_host, is_same_site, norm_text
from .pipeline import Config, _Ctx, _now
from .survey import KeywordSpec, page_text

EVENTS_SCHEMA = 1
PERIOD_START = date(2025, 4, 1)  # 令和7年度の初め(D-137)

LABELS = {
    "date": re.compile(r"日時|日にち|開催日|開催日時|開催期日|期日|実施日|開催期間|日程|期間|とき|大会日"),
    "venue": re.compile(r"会場|場所|開催場所|開催会場|実施場所|ところ"),
    "organizer": re.compile(r"主催|主管|共催|実施主体"),
    "target": re.compile(r"対象|参加資格|参加対象|参加者"),
    "fee": re.compile(r"参加費|参加料|費用|料金|会費|負担金"),
    "entry": re.compile(r"申込|申し込み|申込み|参加申|応募|参加方法"),
    "deadline": re.compile(r"締切|〆切|申込期限|申込期間|受付期間|応募期限|申込み期限|申込締切"),
}
ERA_BASE = {"令和": 2018, "平成": 1988, "R": 2018, "H": 1988, "r": 2018, "h": 1988}

D_ERA = re.compile(r"(令和|平成)\s*(元|\d{1,2})\s*年度?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
D_SEIREKI = re.compile(r"(20\d\d)\s*年度?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
D_ABBR = re.compile(r"(?<![A-Za-z])([RrHh])\s*(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{1,2})")
D_SLASH = re.compile(r"(20\d\d)\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})")
D_MD = re.compile(r"(?<![\d年])(\d{1,2})\s*月\s*(\d{1,2})\s*日")
YEAR_CTX = re.compile(r"(令和|平成)\s*(元|\d{1,2})\s*年度?|(20\d\d)\s*年度?")
CLOSED = re.compile(r"中止|延期|取りやめ|取り止め|開催しません|見送り")
REPORT = re.compile(r"結果|報告|開催しました|を行いました|終了しました|優勝|入賞")
CALENDAR = re.compile(r"カレンダー|イベント情報|行事予定|年間予定|スケジュール|行事一覧|イベント一覧")
MULTI = re.compile(r"総合体育大会|市民体育大会|町民体育大会|村民体育大会|区民体育大会|スポーツ大会|スポーツフェスティバル|スポーツフェスタ|運動会|スポレク|スポーツ祭|健康まつり|ふれあい|市民大会|体育祭|体育大会")


def _year(era: str, n: str) -> int:
    return ERA_BASE[era] + (1 if n == "元" else int(n))


def context_year(text: str) -> int | None:
    """題名・本文の先頭にある『令和7年度』『2025年』から、年の手がかりを取る(月日だけの日付に年をつけるため)。"""
    for m in YEAR_CTX.finditer(text[:600]):
        if m.group(1):
            return _year(m.group(1), m.group(2))
        return int(m.group(3))
    return None


def parse_dates(text: str, ctx_year: int | None = None, limit: int = 4) -> list[date]:
    """文中の日付を、現れた順に返す(年が分からない月日は、ctx_year から。年度の4月より前の月は翌年)。"""
    t = norm_text(text)
    found: list[tuple[int, date]] = []

    def add(pos: int, y: int, mo: int, d: int) -> None:
        try:
            found.append((pos, date(y, mo, d)))
        except ValueError:
            pass

    spans: list[tuple[int, int]] = []
    for m in D_ERA.finditer(t):
        add(m.start(), _year(m.group(1), m.group(2)), int(m.group(3)), int(m.group(4))); spans.append(m.span())
    for m in D_SEIREKI.finditer(t):
        add(m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3))); spans.append(m.span())
    for m in D_ABBR.finditer(t):
        add(m.start(), _year(m.group(1), m.group(2)), int(m.group(3)), int(m.group(4))); spans.append(m.span())
    for m in D_SLASH.finditer(t):
        add(m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3))); spans.append(m.span())
    for m in D_MD.finditer(t):
        if any(a <= m.start() < b for a, b in spans):
            continue
        if ctx_year is None:
            continue
        mo = int(m.group(1))
        y = ctx_year + (1 if mo < 4 and _is_fiscal_ctx(t, ctx_year) else 0)
        add(m.start(), y, mo, int(m.group(2)))
    found.sort(key=lambda x: x[0])
    return [d for _, d in found][:limit]


def _is_fiscal_ctx(text: str, year: int) -> bool:
    return bool(re.search(r"(令和|平成)\s*(元|\d{1,2})\s*年度|20\d\d\s*年度", text[:600]))


def period_of(start: date | None, fiscal_hint: int | None) -> str:
    if start is not None:
        return "期間内" if start >= PERIOD_START else "期間外"
    if fiscal_hint is not None:
        return "期間内" if fiscal_hint >= 2025 else "期間外"
    return "日付不明"


def fiscal_year_of(d: date | None) -> int | None:
    if d is None:
        return None
    return d.year if d.month >= 4 else d.year - 1


def _label_of(key: str) -> str | None:
    k = norm_text(key)
    if len(k) > 14:
        return None
    for name in ("deadline", "date", "venue", "organizer", "fee", "target", "entry"):  # 『申込期限』が『申込』より先
        if LABELS[name].search(k):
            return name
    return None


def kind_of(title: str, body_gg_in_title: bool) -> str:
    if body_gg_in_title:
        return "グラウンドゴルフ専用"
    if CALENDAR.search(title):
        return "カレンダー・予定表"
    if REPORT.search(title):
        return "結果・報告"
    if MULTI.search(title):
        return "複数競技の大会"
    return "その他(ワードの記載あり)"


SITE_NAME_LIKE = re.compile(r"公式|ホームページ|ウェブサイト|Webサイト|トップ|HOME", re.I)
GENERIC_NAME = re.compile(r"^(?:イベント|お知らせ|カレンダー|イベントカレンダー|新着情報|スポーツ|ニュース|トップページ)$")
GENERIC_H2 = re.compile(r"NAV|BreadCrumb|Navigation|ナビ|メニュー|サイト|カテゴリー|関連|フッター|検索|学ぶ|楽しむ|スポーツ$|お問い?合わせ|更新日", re.I)


def page_name_of(soup: BeautifulSoup, raw_title: str, h1t: str, muni_name: str, survey_title: str, spec: KeywordSpec) -> str:
    """イベント名。h1が自治体名・サイト名のとき(吉川市)は、本文の見出し(h2・h3)からイベントらしいものを選ぶ。"""
    def site_like(t: str) -> bool:
        t = norm_text(t)
        return not t or t == muni_name or bool(GENERIC_NAME.match(t)) or (muni_name in t and bool(SITE_NAME_LIKE.search(t))) or len(clean_event_name(t, muni_name)) < 3

    first = clean_event_name(h1t if h1t and not site_like(h1t) else (raw_title or survey_title), muni_name)
    if not site_like(first):
        return first
    heads = [norm_text(h.get_text(" ")) for h in soup.find_all(["h2", "h3"])]
    heads = [t for t in heads if 4 <= len(t) <= 60 and not GENERIC_H2.search(t)]
    for t in heads:
        if spec.in_text(t) or re.search(r"大会|教室|体験|募集|開催|イベント|交流|フェスタ|祭", t):
            return clean_event_name(t, muni_name)
    return first or clean_event_name(survey_title, muni_name)


def clean_event_name(title: str, muni_name: str) -> str:
    n = norm_text(title)
    n = re.split(r"\s*[|｜]\s*|\s+-\s+|\s+–\s+|:\s*" + re.escape(muni_name), n)[0]
    n = re.sub(r"\s*[/／]\s*" + re.escape(muni_name) + r".*$", "", n)
    n = re.sub(r"(?:公式)?(?:ホームページ|ウェブサイト|Webサイト)$", "", n).strip(" -:：　")
    return n[:100]


def _first(pairs: list[tuple[str, str, str]], name: str) -> str:
    for k, v, _ in pairs:
        if _label_of(k) == name and v:
            return _clean_value(norm_text(v))
    return ""


def _clean_value(v: str) -> str:
    """項目の値を整える: 注記(※)と、次の項目の番号(『3.参加人数』)から後ろを落とす。"""
    v = re.split(r"\s*※", v)[0]
    v = re.split(r"\s+\d{1,2}\s*[.．、)）]\s*[^\d\s]", v)[0]
    return v.strip()[:160]


LABEL_LINE = re.compile(
    r"^(?P<label>日時|開催日時|開催日|開催期日|日程|期日|実施日|開催期間|とき|大会日|会場|開催場所|開催会場|実施場所|場所|ところ|主催|主管|共催|実施主体|対象|参加資格|参加対象|"
    r"参加費|参加料|費用|会費|参加方法|申込方法|申込み方法|申し込み方法|申込|申し込み|申込み|参加申込|申込期間|申込期限|申込締切|申込み期限|締切|〆切|受付期間|応募期限)"
    r"(?:[\]】)）][:：\s]*|[:：]|\s|$|[（(])\s*(?P<rest>.*)$"
)
NUMBERING = re.compile(r"^[■●◆▼▽○◎・\[【(（]*\s*(?:[\d]{1,2}[、，.．)）]?\s*)?")
SKIP_DATE_LINE = re.compile(r"更新日|最終更新|公開日|掲載日|作成日|ページID|ページ番号|お問い?合わせ|問合せ")


def _compact_label(line: str) -> str:
    """『2 日 時 令和8年…』『1、日時』のように番号・文字間の空白がある行頭を、ラベルとして読める形にする。"""
    t = NUMBERING.sub("", norm_text(line)).strip()
    return re.sub(r"^((?:[一-龥ぁ-んァ-ヶ]\s){1,3}[一-龥ぁ-んァ-ヶ])(?=\s|[:：]|$)", lambda mm: mm.group(1).replace(" ", ""), t)


def _labeled_lines(body: str) -> dict[str, str]:
    """『日時：10月5日』『2 日 時 令和8年…』『開催日時(改行)2026年6月14日』のような、ラベルの行から値を取る。"""
    out: dict[str, str] = {}
    lines = [l for l in body.split("\n") if norm_text(l)]
    for i, line in enumerate(lines):
        t = _compact_label(line)
        m = LABEL_LINE.match(t)
        if not m:
            continue
        name = _label_of(m.group("label"))
        if not name or name in out:
            continue
        rest = m.group("rest").strip()
        if not rest:  # 値が次の行にある
            nxt = []
            for l2 in lines[i + 1: i + 3]:
                if LABEL_LINE.match(_compact_label(l2)):
                    break
                nxt.append(norm_text(l2))
            rest = " ".join(nxt)
        if rest:
            out[name] = _clean_value(rest)
    return out


COL_ROLES = [
    ("month", re.compile(r"^月$")), ("day", re.compile(r"^日$")),
    ("deadline", re.compile(r"申込締切|締切|〆切|申込期限|申込期間")),
    ("date", re.compile(r"月日|日付|日\(曜日\)|日（曜日）|実施日|開催日|日程|期日|日時|開催期間")),
    ("venue", re.compile(r"会場|場所|開催場所")),
    ("name", re.compile(r"事業名|大会名|行事名|イベント名|イベント\(内容\)|イベント（内容）|名称|行事|種目|内容|事業")),
    ("fee", re.compile(r"参加費|参加料|費用|会費")), ("target", re.compile(r"対象|参加資格")), ("entry", re.compile(r"申込方法|申込|申し込み")),
]


def _table_header(rows) -> tuple[int | None, dict[int, str]]:
    """表の見出し行(先頭の3行まで)を探し、列ごとの役割(日付・会場・名称など)を返す。役割が2つ以上ある行を見出しとする。"""
    for hi, tr in enumerate(rows[:3]):
        head = [re.sub(r"\s", "", norm_text(c.get_text(" "))) for c in tr.find_all(["th", "td"])]
        if len(head) < 3:
            continue
        roles: dict[int, str] = {}
        used: set[str] = set()
        for i, h in enumerate(head):
            for name, pat in COL_ROLES:
                if name not in used and pat.search(h):
                    roles[i] = name
                    used.add(name)
                    break
        if len(used) >= 2 and ("name" in used or "date" in used or "month" in used):
            return hi, {i: roles.get(i, "") for i in range(len(head))}
    return None, {}


def _calendar_date(lines: list[str], i: int, ctx: int | None) -> str:
    """『31日』『土曜日』のように日付が別の行にあるカレンダーで、直前の『2026年10月』と日の行から日付の文を作る。"""
    day = ""
    for j in range(i, max(-1, i - 4), -1):
        m = re.match(r"^(\d{1,2})\s*日$", lines[j])
        if m:
            day = m.group(1)
            break
    if not day:
        return ""
    for j in range(i, max(-1, i - 80), -1):
        m = re.search(r"(20\d\d)\s*年\s*(\d{1,2})\s*月", lines[j])
        if m:
            return f"{m.group(1)}年{m.group(2)}月{day}日"
    return ""


WEEKDAY_LINE = re.compile(r"^[日月火水木金土]曜(?:日)?$")
DAY_LINE = re.compile(r"^(\d{1,2})\s*日?$")
MONTH_CTX = re.compile(r"^(20\d\d)\s*年(?:\s*[(（][^)）]*[)）])?\s*(\d{1,2})\s*月(?!\s*\d)")
CAL_LABEL = re.compile(r"^(日|時間|場所|会場)$")


def _month_context(lines: list[str], i: int) -> tuple[int, int] | None:
    """行 i より前で最も近い『2026年11月』(『2026年』『(令和8年)11月』が別の行でもよい)。"""
    for j in range(i, max(-1, i - 400), -1):
        m = MONTH_CTX.match(" ".join(lines[j: j + 4]))
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def calendar_events(lines: list[str], spec: KeywordSpec, base: dict, page_name: str, ctx_year: int | None = None) -> list[dict]:
    """カレンダー・予定表(日付の見出しの行の下にイベントが並ぶ型。福山市・さつま町)から、グラウンドゴルフのイベントを取る。
    日付=直前の『N日(+曜日)』の行と、直前の『2026年11月』。期間の『日』、『時間』『場所』の項目があれば取る。同じイベントは1つ。"""
    events: list[dict] = []
    seen: set[tuple] = set()
    day = None
    for i, l in enumerate(lines):
        m = DAY_LINE.match(l)
        if m and i + 1 < len(lines) and WEEKDAY_LINE.match(lines[i + 1]):
            day = int(m.group(1))
            continue
        if not spec.find_affirmative(l) or len(l) > 120 or CAL_LABEL.match(l):
            continue
        if i > 0 and CAL_LABEL.match(lines[i - 1]) and lines[i - 1] in ("場所", "会場"):
            continue  # 『場所』の値(会場名にグラウンドゴルフ場が入る)は、イベントの名前ではない
        info: dict[str, str] = {}
        j = i + 1
        while j < min(i + 10, len(lines)):
            if DAY_LINE.match(lines[j]) and j + 1 < len(lines) and WEEKDAY_LINE.match(lines[j + 1]):
                break
            if CAL_LABEL.match(lines[j]) and j + 1 < len(lines):
                info.setdefault(lines[j], lines[j + 1])
                j += 2
                continue
            if j > i + 1 and not CALENDAR_CATEGORY.search(lines[j]) and lines[j] not in info.values() and not CAL_LABEL.match(lines[j - 1] if j else ""):
                break  # 次のイベントの題名
            j += 1
        date_text = info.get("日", "")
        ctx = _month_context(lines, i)
        if not date_text and day and ctx:
            date_text = f"{ctx[0]}年{ctx[1]}月{day}日"
        if not date_text:  # 日付の見出しの型でないカレンダー: 同じ行、無ければ直前の2行の日付
            date_text = l if parse_dates(l, ctx_year) else " ".join(lines[max(0, i - 2): i + 1])
        key = (l[:60], date_text, info.get("場所", ""))
        if key in seen:
            continue
        seen.add(key)
        events.append(_make(base, source="line", event_name=_line_name(l, spec, page_name), **{"_f": {"date": date_text, "venue": info.get("場所", info.get("会場", ""))}}, evidence=_evidence(l, spec)))
        if len(events) >= 30:
            break
    return events


CALENDAR_CATEGORY = re.compile(r"^(?:催し|講座|スポーツ|募集|お知らせ|子育て|シニア|文化施設|健康|医療|福祉|相談|その他)")


def _cell_values(cells: list[str], head: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h, c in zip(head, cells):
        name = _label_of(h)
        if name and c and name not in out:
            out[name] = c[:160]
    return out


def _evidence(text: str, spec: KeywordSpec, width: int = 60) -> str:
    t = norm_text(text)
    ms = spec.find(t)
    if not ms:
        return ""
    return t[max(0, ms[0].start() - width): ms[0].end() + width]


def _make(base: dict, **kw) -> dict:
    ev = dict(base)
    ev.update({k: v for k, v in kw.items() if v is not None})
    return ev


def extract_events(html: str, muni_name: str, spec: KeywordSpec, survey_title: str = "") -> dict:
    soup = parse_html(html)
    raw_title = norm_text(soup.title.get_text(" ")) if soup.title else ""
    h1 = soup.find("h1")
    h1t = norm_text(h1.get_text(" ")) if h1 else ""
    inquiry = _inquiry(soup)
    title, body = page_text(soup)
    pairs = _kv_pairs(soup)
    labeled = _labeled_lines(body)
    page_name = page_name_of(soup, raw_title, h1t, muni_name, survey_title, spec)
    gg_title = bool(spec.find_affirmative(f"{raw_title} {h1t}"))
    kind = kind_of(f"{raw_title} {h1t}", gg_title)
    ctx = context_year(f"{raw_title} {h1t} {body[:400]}")
    closed = bool(CLOSED.search(f"{raw_title} {h1t}"))
    base = {
        "event_kind": kind, "contact_dept": inquiry.get("dept", ""), "contact_phone": inquiry.get("phone", ""),
        "status_note": "中止・延期" if closed else "",
    }
    events: list[dict] = []

    def fields_from(src: dict[str, str]) -> dict:
        return {k: src.get(k, "") for k in ("date", "venue", "organizer", "target", "fee", "entry", "deadline")}

    page_fields = fields_from({k: _first(pairs, k) or labeled.get(k, "") for k in ("date", "venue", "organizer", "target", "fee", "entry", "deadline")})

    # 表: グラウンドゴルフの語を含む行を、1イベントにする(見出し行の列名から日時・会場などを取る。月・日が別の列、行の結合で先頭の列が省かれる表にも対応)
    tables_used = False
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        hi, roles = _table_header(rows)
        if hi is None:
            continue
        head_n = len(roles)
        carried: list[str] = []
        for tr in rows[hi + 1:]:
            cells = [norm_text(c.get_text(" ")) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            if len(cells) < head_n and carried:
                lead = [i for i in range(head_n) if roles.get(i) in ("month", "date", "day")]
                missing = head_n - len(cells)
                if lead and lead == list(range(len(lead))) and missing <= len(lead):
                    cells = carried[:missing] + cells  # 結合された先頭の列(月・日付)は、前の行の値
            if len(cells) == head_n:
                carried = cells[:]
            row_text = " ".join(cells)
            if not spec.find_affirmative(row_text):
                continue
            vals: dict[str, str] = {}
            for i, c in enumerate(cells[:head_n]):
                r_ = roles.get(i)
                if r_ and c and r_ not in vals:
                    vals[r_] = c[:160]
            if vals.get("month") and vals.get("day"):
                vals["date"] = f"{vals['month']}月{vals['day']}日" if not vals["day"].endswith("日") else f"{vals['month']}月{vals['day']}"
            name_cell = vals.get("name") or next((c for c in cells if spec.find(c)), row_text)
            events.append(_make(base, source="table_row", event_name=name_cell[:100], **{"_f": {k: vals.get(k, "") for k in ("date", "venue", "target", "fee", "entry", "deadline")}}, evidence=_evidence(row_text, spec)))
            tables_used = True

    if not tables_used:
        gg_lines = [l for l, _ in spec.find_lines(body)]
        if kind == "カレンダー・予定表":
            # カレンダー・予定表は、グラウンドゴルフの語を含む行を1イベントにする(同じ行、無ければ直前の行の日付を日付とする)
            lines = [norm_text(l) for l in body.split("\n") if norm_text(l)]
            events.extend(calendar_events(lines, spec, base, page_name, ctx))
            seen: set[str] = set()
            for i, l in enumerate(lines):
                if events or not spec.find_affirmative(l) or len(l) > 220 or l[:60] in seen:
                    continue
                seen.add(l[:60])
                near = l if parse_dates(l, ctx) else (_calendar_date(lines, i, ctx) or " ".join(lines[max(0, i - 2): i + 1]))
                events.append(_make(base, source="line", event_name=_line_name(l, spec, page_name), **{"_f": {"date": near}}, evidence=_evidence(l, spec)))
                if len(events) >= 12:
                    break
        if not events:
            # それ以外は、ページ全体を1つのイベントとする(複数競技の大会も1つ。グラウンドゴルフは種目として証拠の文に残す)
            events.append(_make(base, source="page", event_name=page_name, **{"_f": page_fields}, evidence=_evidence(" ".join(gg_lines) or body, spec)))

    out_events = []
    for ev in events:
        f = ev.pop("_f", {})
        date_text = f.get("date", "")
        basis = "項目" if date_text else ""
        ds = parse_dates(date_text, context_year(date_text) or ctx)
        if not ds:
            ds = parse_dates(f"{raw_title} {h1t}", ctx)
            basis = "題名" if ds else basis
        if not ds and ev.get("source") == "page":
            for l in [norm_text(x) for x in body.split("\n") if norm_text(x)][:15]:
                if SKIP_DATE_LINE.search(l):
                    continue
                ds = parse_dates(l, ctx)
                if ds:
                    date_text, basis = l, "本文推定"
                    break
        start, end = (min(ds), max(ds)) if ds else (None, None)
        fy = fiscal_year_of(start) if start else (ctx if (ctx and re.search(r"年度", f"{raw_title} {h1t}")) else None)
        ev.update({
            "date_text": date_text[:120], "date_basis": basis, "date_start": start.isoformat() if start else "", "date_end": end.isoformat() if end else "",
            "fiscal_year": fy or "", "period": period_of(start, fy),
            "venue": f.get("venue", ""), "organizer": f.get("organizer", ""), "target": f.get("target", ""),
            "fee": f.get("fee", ""), "entry": f.get("entry", ""), "deadline": f.get("deadline", ""),
        })
        out_events.append(ev)
    return {"title": (raw_title or title)[:100], "page_name": page_name, "event_kind": kind, "events": out_events}


def _line_name(line: str, spec: KeywordSpec, fallback: str) -> str:
    """行がそのままイベント名らしいとき(短い)は行を、長い文のときはページ名を使う。"""
    l = re.sub(r"^[■●◆▼・\s\d.月日()（）/～~\-]+", "", norm_text(line)).strip()
    return (l if 4 <= len(l) <= 40 and spec.find(l) else fallback)[:100]


EVENT_COLUMNS = [
    "prefecture", "municipality_code", "municipality_name", "event_name", "event_kind", "date_text", "date_basis", "date_start", "date_end", "fiscal_year", "period",
    "venue", "organizer", "target", "fee", "entry", "deadline", "contact_dept", "contact_phone", "status_note", "evidence",
    "page_title", "page_url", "source", "site_url", "events_route", "extracted_at",
]


def event_rows(rec: dict) -> list[dict]:
    m = rec["municipality"]
    rows = []
    for pg in rec["pages"]:
        for ev in pg.get("events", []):
            rows.append({
                "prefecture": m["prefecture"], "municipality_code": m["code"], "municipality_name": m["name"],
                **{k: ev.get(k, "") for k in EVENT_COLUMNS[3:21]},
                "page_title": pg["title"], "page_url": pg["page_url"], "source": ev.get("source", ""), "site_url": m["official_url"],
                "events_route": rec["run"]["route"], "extracted_at": rec["run"]["finished_at"],
            })
    return rows


class EventsConfig:
    def __init__(self, route: str = "local", max_pages: int = 60, retry_wait: float = 2.0):
        self.route, self.max_pages, self.retry_wait = route, max_pages, retry_wait

    def pipeline_config(self) -> Config:
        return Config(route=self.route, max_requests=self.max_pages + 4, retry_wait=self.retry_wait)


def events_municipality(m: Municipality, pages: list[dict], fetcher: Fetcher, spec: KeywordSpec, cfg: EventsConfig) -> dict:
    out = {
        "schema_version": EVENTS_SCHEMA, "keyword": spec.name,
        "municipality": {"code": m.code, "name": m.name, "prefecture": m.prefecture_name, "official_url": m.url},
        "run": {"route": cfg.route, "crawler_version": __version__, "started_at": _now(), "finished_at": ""},
        "outcome": "", "failure_class": "", "pages": [], "requests": [],
    }
    ctx = _Ctx(fetcher, cfg.pipeline_config())
    try:
        if not pages:
            out["outcome"] = "no_pages"
            return out
        robots = ctx.load_robots(m.url)
        if robots.unreachable:
            out["outcome"], out["failure_class"] = "fetch_failed", "robots_unreachable"
            return out
        site_host = base_host(m.url)
        for pg in pages[: cfg.max_pages]:
            res = ctx.get(pg["page_url"])
            rec = {"page_url": pg["page_url"], "survey_title": pg.get("page_title", ""), "status": res.status, "error_class": res.error_class}
            if res.error_class == "budget_exceeded":
                break
            if not res.ok or (res.content_type and "html" not in res.content_type.lower()) or not is_same_site(res.final_url, site_host):
                out["pages"].append(rec)
                continue
            rec.update(extract_events(decode_bytes(res.body, res.content_type), m.name, spec, pg.get("page_title", "")))
            rec["matched_text"] = pg.get("matched_text", "")
            out["pages"].append(rec)
        out["outcome"] = "extracted"
    finally:
        out["requests"] = ctx.log
        out["run"]["finished_at"] = _now()
        out["run"]["request_count"] = len(ctx.log)
    return out


def write_events(root: Path, rec: dict, prefecture_code: str) -> Path:
    path = Path(root) / rec["keyword"] / rec["run"]["route"] / prefecture_code / f"{rec['municipality']['code']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def load_events(root: Path, keyword: str, route: str) -> list[dict]:
    base = Path(root) / keyword / route
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("*/*.json"))]
