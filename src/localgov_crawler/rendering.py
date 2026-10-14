"""JS描画が必要そうかの判定(HTTP取得した本文が極端に少ないなど)。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

SPA_ROOT = re.compile(r"""id=["'](app|root|__next|__nuxt)["']|ng-app|data-reactroot""", re.I)


@dataclass
class RenderAssessment:
    text_length: int
    anchor_count: int
    script_count: int
    noscript_text_length: int
    image_count: int
    needs_headless: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "anchor_count": self.anchor_count,
            "script_count": self.script_count,
            "noscript_text_length": self.noscript_text_length,
            "image_count": self.image_count,
            "needs_headless": self.needs_headless,
            "reasons": self.reasons,
            "provenance": "auto",
        }


def assess_rendering(html: str, soup: BeautifulSoup) -> RenderAssessment:
    anchors = len(soup.find_all("a", href=True))
    scripts = len(soup.find_all("script"))
    images = len(soup.find_all("img"))
    noscript_len = sum(len(n.get_text(strip=True)) for n in soup.find_all("noscript"))
    clone = BeautifulSoup(html, "lxml")
    for t in clone(["script", "style", "noscript", "template"]):
        t.decompose()
    text_len = len(re.sub(r"\s+", "", clone.get_text()))
    reasons = []
    # 画像が主体の静的ポータル(リンクが画像だけ)はJS描画ではないので除く
    if text_len < 300 and anchors < 10 and images < 3:
        reasons.append("body_text_and_links_scarce")
    if SPA_ROOT.search(html) and text_len < 500:
        reasons.append("spa_root_with_little_text")
    if noscript_len > text_len and noscript_len > 100:
        reasons.append("noscript_dominant")
    return RenderAssessment(text_len, anchors, scripts, noscript_len, images, bool(reasons), reasons)
