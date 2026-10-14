"""robots.txtの取得結果の解釈。RFC 9309に沿い、4xxは制限なし、5xx/接続失敗は全面禁止扱い。"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

from .fetcher import PRODUCT_TOKEN, FetchResult


@dataclass
class RobotsInfo:
    status: int | None = None
    error_class: str = ""
    available: bool = False  # 200で取得できた
    unreachable: bool = False  # 5xx・接続失敗(安全側で全面禁止扱い)
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    disallow_count: int = 0
    disallow_all: bool = False
    text: str = ""
    _parser: RobotFileParser | None = None

    def can_fetch(self, url: str) -> bool:
        if self.unreachable:
            return False
        if self._parser is None:
            return True
        return self._parser.can_fetch(PRODUCT_TOKEN, url)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "error_class": self.error_class,
            "available": self.available,
            "unreachable": self.unreachable,
            "crawl_delay": self.crawl_delay,
            "sitemaps": self.sitemaps,
            "disallow_count": self.disallow_count,
            "disallow_all": self.disallow_all,
            "text": self.text[:20000],
        }


def parse_robots(res: FetchResult) -> RobotsInfo:
    info = RobotsInfo(status=res.status, error_class=res.error_class)
    if res.status is None or res.status >= 500:
        info.unreachable = True
        return info
    if res.status != 200:
        return info  # 404などは制限なし
    from .html import decode_bytes

    text = decode_bytes(res.body, res.content_type)
    info.available = True
    info.text = text
    lines = text.splitlines()
    rp = RobotFileParser()
    rp.parse(lines)
    info._parser = rp
    delay = rp.crawl_delay(PRODUCT_TOKEN)
    info.crawl_delay = float(delay) if delay is not None else None
    info.sitemaps = list(rp.site_maps() or [])
    # 自分に適用されるグループのDisallow数を数える(*または自分のトークン)
    applies = False
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            applies = value == "*" or PRODUCT_TOKEN in value.lower()
        elif key == "disallow" and applies and value:
            info.disallow_count += 1
            if value == "/":
                info.disallow_all = True
    return info
