"""トップページ等からのリンク抽出(ナビゲーションの文言とURL)。"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

# 自治体サイトでよくあるメニュー区分の見出し
MENU_MARKERS = [
    "分野別", "ライフシーン", "ライフステージ", "組織別", "部署", "目的別", "くらし", "暮らし",
    "子育て", "健康・福祉", "観光", "文化・スポーツ", "事業者", "行政情報", "市政", "町政", "村政",
    "施設案内", "公共施設", "よくある質問", "申請", "手続き",
]
_REGION_HINT = re.compile(r"nav|menu|global|gnav|header|footer|sidebar|side", re.I)
_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "sms:", "data:")
_SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|svg|webp|ico|css|js|zip|xlsx?|docx?|pptx?)(\?|$)", re.I)


@dataclass
class Link:
    text: str
    url: str
    region: str  # nav / header / footer / main / aside / other
    same_site: bool
    is_pdf: bool = False
    text_kind: str = "text"  # text / img_alt / img_src(画像のみ。ファイル名を仮ラベルにした)

    def to_dict(self) -> dict:
        return asdict(self)


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def base_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_same_site(url: str, site_host: str) -> bool:
    host = base_host(url)
    return bool(host) and (host == site_host or host.endswith("." + site_host))


def _region(a: Tag) -> str:
    for parent in a.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name in ("nav", "header", "footer", "main", "aside"):
            return parent.name
        ident = " ".join(filter(None, [parent.get("id", ""), " ".join(parent.get("class", []))]))
        if ident and _REGION_HINT.search(ident):
            low = ident.lower()
            if "footer" in low:
                return "footer"
            if "header" in low:
                return "header"
            return "nav"
    return "other"


def _link_text(a: Tag) -> tuple[str, str]:
    text = norm_text(a.get_text(" "))
    if text:
        return text, "text"
    img = a.find("img", alt=True)
    if img and img["alt"].strip():
        return norm_text(img["alt"]), "img_alt"
    label = norm_text(a.get("title", "") or a.get("aria-label", ""))
    if label:
        return label, "text"
    # alt無しの画像リンク: ファイル名(拡張子なし)を仮ラベルにする。リンク先が分かればナビとして使える
    img = a.find("img", src=True)
    if img:
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", img["src"].split("?", 1)[0].rsplit("/", 1)[-1])
        if stem:
            return stem, "img_src"
    return "", "text"


def extract_links(soup: BeautifulSoup, page_url: str, site_host: str) -> list[Link]:
    seen: set[tuple[str, str]] = set()
    out: list[Link] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(_SKIP_SCHEMES):
            continue
        url, _ = urldefrag(urljoin(page_url, href))
        if urlsplit(url).scheme not in ("http", "https") or _SKIP_EXT.search(url):
            continue
        text, kind = _link_text(a)
        if not text:
            continue
        key = (url, text)
        if key in seen:
            continue
        seen.add(key)
        out.append(Link(text, url, _region(a), is_same_site(url, site_host), urlsplit(url).path.lower().endswith(".pdf"), kind))
    return out


def find_menu_labels(soup: BeautifulSoup) -> list[str]:
    """見出し・ボタン・リンク文言に現れるメニュー区分を拾う(分野別/ライフシーン別 など)。"""
    texts = [norm_text(t.get_text(" ")) for t in soup.find_all(["h1", "h2", "h3", "h4", "h5", "dt", "button", "summary", "a"])]
    found = []
    for marker in MENU_MARKERS:
        if any(marker in t and len(t) <= 30 for t in texts):
            found.append(marker)
    return found
