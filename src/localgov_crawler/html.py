"""HTMLのデコードとパース補助。"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-]+)""", re.I)
_HEADER_CHARSET = re.compile(r"charset\s*=\s*([A-Za-z0-9_\-]+)", re.I)

_ALIASES = {"shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932", "euc-jp": "euc_jp"}


def decode_bytes(body: bytes, content_type: str = "") -> str:
    """ヘッダ→meta→UTF-8→CP932の順で文字コードを推定する(古い自治体サイトはShift_JIS/EUC-JPが残る)。"""
    candidates: list[str] = []
    m = _HEADER_CHARSET.search(content_type or "")
    if m:
        candidates.append(m.group(1))
    m2 = _META_CHARSET.search(body[:4096])
    if m2:
        candidates.append(m2.group(1).decode("ascii", "ignore"))
    candidates += ["utf-8", "cp932", "euc_jp"]
    for c in candidates:
        enc = _ALIASES.get(c.lower(), c)
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


def parse_html(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "lxml")
