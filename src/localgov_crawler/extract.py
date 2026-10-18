"""ワード調査で見つかった『場所(施設)』のページから、施設の名前・住所・電話番号・問い合わせ先を取り出す(D-124)。
ルールだけで取り出す(AIは使わない、D-050)。ページは取得し直す(HTMLは保存していないため)。
保存するのは、名前・住所・電話番号・問い合わせ先の課名と、ワードの前後の短い文だけ(本文の転載はしない)。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from . import __version__
from .fetcher import Fetcher
from .html import decode_bytes, parse_html
from .municipalities import Municipality
from .nav import base_host, is_same_site, norm_text
from .pipeline import Config, _Ctx, _now
from .survey import KeywordSpec

EXTRACT_SCHEMA = 1

# 電話番号: 市外局番から始まる10〜11桁(NFKC正規化後)。郵便番号(〒・郵便の直後)は除く
PHONE = re.compile(r"(?<![\d-])(0\d{1,4})[-(（)）\s]{1,2}(\d{1,4})[-)）\s]{1,2}(\d{3,4})(?![\d-])")
POSTAL = re.compile(r"(?:〒|郵便番号?[:：]?)\s*\d{3}-\d{4}")
ADDRESS_KEY = re.compile(r"^(?:所在地|住所|所在|場所|位置|施設所在地|所在地・アクセス|所在地・電話)(?:\s|（.*）|\(.*\))?$")
PHONE_KEY = re.compile(r"電話|TEL|Tel|tel|連絡先|問い?合わせ|お問合せ")
NAME_KEY = re.compile(r"^(?:施設名|名称|施設の名称|名前)$")
CONTACT_HEADING = re.compile(r"お?問い?合わせ|連絡先|担当|^.{1,12}[係課室部班]\\s*(?:\\(.*\\))?$|このページ|この記事")
GENERIC_HEADING = re.compile(r"^(?:施設概要|施設情報|基本情報|概要|アクセス|お問い合わせ|問い合わせ|利用案内|利用方法|料金|設備|施設の概要|施設案内|ご利用案内|所在地|地図|関連情報|その他|注意事項|備考|利用できる種目|主な設備)$")
SITE_WORDS = re.compile(r"公式|ホームページ|ウェブサイト|Webサイト|市役所|町役場|村役場|トップページ")
INQUIRY_MARK = re.compile(r"お?問い?合わせ(?:先)?|担当(?:課|部署)?|連絡先")
ADDRESS_CUT = re.compile(r"(?:\s*(?:電話|TEL|Tel|ＴＥＬ|tel)|\s*[（(【\[]?地図|\s*駐車場|\s*Google|\s*アクセス|\s*開館|\s*利用時間|\s*休館).*$")
JP_PREFIX = re.compile(r"^(?:〒\s*\d{3}-\d{4}\s*)?(?:北海道|東京都|京都府|大阪府|[^\s]{2,3}県)?")


def _norm_phone(m: re.Match) -> str:
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def find_phones(text: str) -> list[str]:
    t = norm_text(text)
    t = POSTAL.sub(" ", t)
    out = []
    for m in PHONE.finditer(t):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) in (10, 11) and _norm_phone(m) not in out:
            out.append(_norm_phone(m))
    return out


PREFECTURE_PREFIX = re.compile(r"^(?:北海道|東京都|京都府|大阪府|\S{2,3}県)\s*")


def clean_address(value: str) -> str:
    """住所の値から、郵便番号・都道府県の前置き・続く説明(設備・料金・地図など)を落とし、最初の1まとまりにする。"""
    v = norm_text(value)
    v = re.sub(r"^〒\s*\d{3}-\d{4}\s*", "", v)
    v = PREFECTURE_PREFIX.sub(lambda m: m.group(0).strip(), v)
    v = ADDRESS_CUT.sub("", v).strip(" 　:：、,")
    tokens = v.split()
    if not tokens:
        return ""
    out = tokens[0]
    if len(tokens) > 1 and not re.search(r"\d", out) and re.search(r"\d", tokens[1]) and len(out) <= 12 and not re.search(r"設備|料金|利用|施設", tokens[1]):
        out += tokens[1]  # 『春日部市 牛島626』のように途中で空白が入る住所
    return out[:80]


def looks_like_address(v: str) -> bool:
    """市区町村郡の名前を含む(『クラブハウス』『現場事務所』のような場所の名前は住所でない)。"""
    return bool(re.search(r"[市区町村郡]", v)) and not re.search(r"クラブハウス|事務所|管理棟|受付|売店", v)


def clean_name(title: str, muni_name: str) -> str:
    segs = [s.strip() for s in re.split(r"\s*[|｜/／]\s*|\s+[-–—－]\s+", norm_text(title)) if s.strip()]
    segs = [s for s in segs if s != muni_name and not SITE_WORDS.search(s)]
    name = segs[0] if segs else norm_text(title)
    name = re.sub(r"^施設案内\s*", "", name)
    return name[:80]


@dataclass
class _Item:
    name: str = ""
    address: str = ""
    phone: str = ""
    source: str = ""
    text: str = ""  # ワードの有無を見るための、この項目の文

    def ok(self) -> bool:
        return bool(self.address or self.phone)


def _cells(tr) -> list[str]:
    return [norm_text(c.get_text(" ")) for c in tr.find_all(["th", "td"])]


def _table_items(soup: BeautifulSoup, spec: KeywordSpec | None) -> list[_Item]:
    """見出しの行に『施設名』『住所/所在地』『電話』がある一覧表。1行を1施設にする。"""
    items: list[_Item] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        head = _cells(rows[0])
        idx = {"name": None, "address": None, "phone": None}
        for i, h in enumerate(head):
            if idx["name"] is None and re.search(r"施設名|名称|名前|施設", h):
                idx["name"] = i
            elif idx["address"] is None and re.search(r"所在地|住所|場所", h):
                idx["address"] = i
            elif idx["phone"] is None and re.search(r"電話|TEL|連絡先|問い?合わせ", h, re.I):
                idx["phone"] = i
        if idx["name"] is None or (idx["address"] is None and idx["phone"] is None):
            continue
        for tr in rows[1:]:
            cells = _cells(tr)
            if len(cells) < 2:
                continue
            g = lambda k: cells[idx[k]] if idx[k] is not None and idx[k] < len(cells) else ""
            phones = find_phones(g("phone")) if idx["phone"] is not None else find_phones(" ".join(cells))
            addr = clean_address(g("address")) if idx["address"] is not None and looks_like_address(g("address")) else ""
            items.append(_Item(name=g("name")[:80], address=addr, phone=phones[0] if phones else "", source="table_row", text=" ".join(cells)))
    return items


def _kv_pairs(soup: BeautifulSoup) -> list[tuple[str, str, str]]:
    """(キー, 値, 直前の見出し) の組。2列の表(th/td)、定義リスト(dt/dd)、『キー:値』の行から集める。"""
    pairs: list[tuple[str, str, str]] = []

    def heading_of(tag) -> str:
        h = tag.find_previous(["h1", "h2", "h3", "h4"])
        return norm_text(h.get_text(" ")) if h else ""

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) == 2:
            pairs.append((norm_text(cells[0].get_text(" ")), norm_text(cells[1].get_text(" ")), heading_of(tr)))
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd is not None:
            pairs.append((norm_text(dt.get_text(" ")), norm_text(dd.get_text(" ")), heading_of(dt)))
    for el in soup.find_all(["p", "li", "div"]):
        if el.find(["p", "li", "div", "table", "ul"]):
            continue  # 入れ子の外側は見ない(内側で拾う)
        t = norm_text(el.get_text(" "))
        m = re.match(r"^[■●◆▼・\[【(（]?\s*([^:：]{1,10})\s*[\]】)）]?\s*[:：]\s*(.+)$", t)
        if m and len(t) < 200:
            pairs.append((m.group(1).strip(), m.group(2).strip(), heading_of(el)))
    return pairs


def _kv_items(pairs: list[tuple[str, str, str]], page_name: str) -> list[_Item]:
    by_heading: dict[str, _Item] = {}
    order: list[str] = []
    for key, value, heading in pairs:
        if CONTACT_HEADING.search(heading) or CONTACT_HEADING.search(key) and not ADDRESS_KEY.match(key) and not PHONE_KEY.search(key):
            continue  # 問い合わせ先の欄は施設ではない(問い合わせ先として別に取る)
        item = by_heading.get(heading)
        if item is None:
            name = page_name if (not heading or GENERIC_HEADING.match(heading) or heading == page_name) else heading
            item = by_heading[heading] = _Item(name=name[:80], source="kv")
            order.append(heading)
        if ADDRESS_KEY.match(key) and not item.address and looks_like_address(value):
            item.address = clean_address(value)
        elif PHONE_KEY.search(key) and not item.phone:
            ph = find_phones(value)
            if ph:
                item.phone = ph[0]
        item.text += f" {key} {value}"
    return [by_heading[h] for h in order if by_heading[h].ok()]


def _inquiry(soup: BeautifulSoup) -> dict:
    """ページの『お問い合わせ先』の欄(担当課と電話番号)。ページの最後のほうにあるものを採る。"""
    best: dict = {}
    for el in soup.find_all(["div", "p", "section", "footer", "dl", "address", "li"]):
        if el.find(["div", "section", "footer", "table"]):
            continue
        t = norm_text(el.get_text(" "))
        if len(t) > 250 or not INQUIRY_MARK.search(t):
            continue
        phones = find_phones(t)
        if not phones:
            continue
        dept = re.sub(r"^(?:お?問い?合わせ(?:先)?|担当(?:課|部署)?|連絡先)\s*[:：]?\s*", "", t.split(phones[0].split("-")[0])[0]).strip(" :：　")
        dept = re.sub(r"\s*(?:電話|TEL|Tel|FAX|ファックス|所在地|住所|〒|メール|E-?mail|\d{3}-\d{4}).*$", "", dept).strip()
        dept = re.sub(r"^(?:このページ(?:に関する|について)?|この記事(?:に関する|について)?)\s*(?:お?問い?合わせ(?:先)?)?\s*", "", dept).strip(" :：　")
        best = {"dept": dept[:60], "phone": phones[0]}
    return best


def extract_page(html: str, muni_name: str, spec: KeywordSpec | None = None) -> dict:
    soup = parse_html(html)
    title = norm_text(soup.title.get_text(" ")) if soup.title else ""
    h1 = soup.find("h1")
    h1t = norm_text(h1.get_text(" ")) if h1 else ""
    page_name = clean_name(h1t if h1t and h1t != muni_name else title, muni_name)
    items = _table_items(soup, spec)
    source = "table"
    if not items:
        items = _kv_items(_kv_pairs(soup), page_name)
        source = "kv"
    if not items:
        text = norm_text(soup.get_text(" "))
        phones = find_phones(text)
        addr = ""
        m = re.search(r"(?:所在地|住所)\s*[:：]?\s*([^\s].{5,100})", text)
        if m and looks_like_address(m.group(1)):
            addr = clean_address(m.group(1))
        if addr or phones:
            items = [_Item(name=page_name, address=addr, phone=phones[0] if phones else "", source="text", text=text[:400])]
    if len(items) == 1 and not items[0].phone:  # 1施設のページで、施設の欄に電話が無ければ、『電話』『問い合わせ』などの語のある文の電話番号を使う
        for el in soup.find_all(["p", "li", "dd", "td", "div", "span"]):
            if el.find(["p", "li", "div", "table"]):
                continue
            t = norm_text(el.get_text(" "))
            if len(t) <= 200 and PHONE_KEY.search(t):
                ph = find_phones(t)
                if ph:
                    items[0].phone = ph[0]
                    items[0].source += "+text_phone"
                    break
    gg = [bool(spec and spec.find_affirmative(it.text)) for it in items] if spec is not None else [False] * len(items)
    return {
        "title": title[:100], "page_name": page_name, "multi_facility": len(items) > 1, "item_source": source,
        "items": [{"name": it.name or page_name, "address": it.address, "phone": it.phone, "source": it.source, "keyword_in_item": g} for it, g in zip(items, gg)],
        "inquiry": _inquiry(soup),
    }


@dataclass
class ExtractConfig:
    route: str = "local"
    max_pages: int = 60  # 1自治体あたり取得するページ数の上限(通常は数ページ)
    retry_wait: float = 2.0

    def pipeline_config(self) -> Config:
        return Config(route=self.route, max_requests=self.max_pages + 4, retry_wait=self.retry_wait)


def extract_municipality(m: Municipality, pages: list[dict], fetcher: Fetcher, spec: KeywordSpec, cfg: ExtractConfig) -> dict:
    out = {
        "schema_version": EXTRACT_SCHEMA, "keyword": spec.name,
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
            rec.update(extract_page(decode_bytes(res.body, res.content_type), m.name, spec))
            rec["matched_text"] = pg.get("matched_text", "")
            out["pages"].append(rec)
        out["outcome"] = "extracted"
    finally:
        out["requests"] = ctx.log
        out["run"]["finished_at"] = _now()
        out["run"]["request_count"] = len(ctx.log)
    return out


def write_extract(root: Path, rec: dict, prefecture_code: str) -> Path:
    path = Path(root) / rec["keyword"] / rec["run"]["route"] / prefecture_code / f"{rec['municipality']['code']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_extracts(root: Path, keyword: str, route: str) -> list[dict]:
    base = Path(root) / keyword / route
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("*/*.json"))]


DETAIL_COLUMNS = ["prefecture", "municipality_code", "municipality_name", "facility_name", "address", "phone", "inquiry_dept", "inquiry_phone",
                  "page_title", "page_url", "multi_facility", "keyword_in_item", "matched_text", "item_source", "site_url", "extract_route", "extracted_at"]


def detail_rows(rec: dict) -> list[dict]:
    m = rec["municipality"]
    rows = []
    for pg in rec["pages"]:
        if "items" not in pg:
            continue
        items = pg["items"]
        if pg["multi_facility"] and any(i["keyword_in_item"] for i in items):
            items = [i for i in items if i["keyword_in_item"]]  # 一覧のページは、ワードのある施設の行だけにする
        inq = pg.get("inquiry") or {}
        if not items:
            items = [{"name": pg["page_name"], "address": "", "phone": "", "source": "none", "keyword_in_item": False}]
        for i in items:
            rows.append({
                "prefecture": m["prefecture"], "municipality_code": m["code"], "municipality_name": m["name"], "facility_name": i["name"], "address": i["address"],
                "phone": i["phone"], "inquiry_dept": inq.get("dept", ""), "inquiry_phone": inq.get("phone", ""), "page_title": pg["title"], "page_url": pg["page_url"],
                "multi_facility": "1" if pg["multi_facility"] else "", "keyword_in_item": "1" if i["keyword_in_item"] else "", "matched_text": pg.get("matched_text", ""),
                "item_source": i["source"], "site_url": m["official_url"], "extract_route": rec["run"]["route"], "extracted_at": rec["run"]["finished_at"],
            })
    return rows
