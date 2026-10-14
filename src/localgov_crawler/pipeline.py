"""1自治体の浅い構造解析。トップ → robots.txt → サイトマップ → CMS/JS判定 → ナビ → ハブ候補(2階層まで)。"""
from __future__ import annotations

import gzip
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__, hub
from .cms import detect_cms
from .fetcher import FetchResult, Fetcher
from .html import decode_bytes, parse_html
from .municipalities import Municipality
from .nav import base_host, extract_links, find_menu_labels, is_same_site
from .rendering import assess_rendering
from .robots import RobotsInfo, parse_robots
from .sitemap import UrlTally, parse_sitemap

SCHEMA_VERSION = 1
RETRYABLE = {"timeout", "conn_reset", "http_408", "http_429", "http_5xx"}


@dataclass
class Config:
    route: str = "local"  # actions_direct / proxy / local など。取得経路の比較に使う
    max_requests: int = 30
    d1_fetch: int = 6  # トップのリンクから先を取得する候補ページ数
    d2_fetch: int = 3  # さらにその先(候補ページ内のリンク)を取得する数
    d2_min_score: int = 5
    sitemap_attempts: int = 3
    sitemap_children: int = 5
    retry_wait: float = 2.0  # 一時的な失敗の再試行までの待ち(秒)
    save_html_dir: Path | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Ctx:
    """リクエスト予算・robots確認・ログ記録をまとめる。"""

    def __init__(self, fetcher: Fetcher, cfg: Config):
        self.fetcher, self.cfg = fetcher, cfg
        self.log: list[dict] = []
        self.robots: dict[str, RobotsInfo] = {}

    def robots_for(self, url: str) -> RobotsInfo | None:
        return self.robots.get((urlsplit(url).hostname or "").lower())

    def get(self, url: str, check_robots: bool = True) -> FetchResult:
        if len(self.log) >= self.cfg.max_requests:
            return FetchResult(url, url, error_class="budget_exceeded")
        if check_robots:
            info = self.robots_for(url)
            if info is not None and not info.can_fetch(url):
                return FetchResult(url, url, error_class="robots_disallowed")
        res = self.fetcher.get(url)
        self.log.append(res.log_entry())
        # 一時的な失敗は1回だけ再試行する。Retry-Afterが長い(30秒超)ときは従って諦める
        if res.error_class in RETRYABLE and len(self.log) < self.cfg.max_requests:
            wait = res.retry_after if res.retry_after is not None else self.cfg.retry_wait
            if wait <= 30:
                time.sleep(wait)
                res = self.fetcher.get(url)
                entry = res.log_entry()
                entry["retry"] = True
                self.log.append(entry)
        return res

    def load_robots(self, url: str) -> RobotsInfo:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if host in self.robots:
            return self.robots[host]
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        res = self.get(robots_url, check_robots=False)
        info = parse_robots(res)
        if info.crawl_delay:
            self.fetcher.set_host_delay(host, info.crawl_delay)
        self.robots[host] = info
        return info


def _empty_result(m: Municipality, cfg: Config, started: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "municipality": {
            "code": m.code, "name": m.name, "full_name": m.full_name, "prefecture": m.prefecture_name,
            "kind": m.kind, "scope": m.scope, "official_url": m.url,
        },
        "run": {"route": cfg.route, "crawler_version": __version__, "started_at": started, "finished_at": ""},
        "outcome": "", "failure_class": "", "needs_review": [], "ai_needed": False,
        "site_profile": {}, "nav_links": [], "menu_labels": [], "genre_entrypoints": [], "requests": [],
    }


def analyze(m: Municipality, fetcher: Fetcher, cfg: Config | None = None) -> dict:
    cfg = cfg or Config()
    result = _empty_result(m, cfg, _now())
    ctx = _Ctx(fetcher, cfg)
    try:
        _analyze(m, ctx, cfg, result)
    finally:
        result["requests"] = ctx.log
        result["run"]["finished_at"] = _now()
        result["run"]["request_count"] = len(ctx.log)
        result["run"]["elapsed_ms"] = sum(r["elapsed_ms"] for r in ctx.log)
    return result


def _analyze(m: Municipality, ctx: _Ctx, cfg: Config, result: dict) -> None:
    if not m.url:
        result["outcome"] = "no_url"
        return
    profile = result["site_profile"] = {"fetch_method": "http", "used_proxy": ctx.fetcher.used_proxy}

    # 1. robots.txt → トップページ
    robots = ctx.load_robots(m.url)
    profile["robots"] = robots.to_dict()
    if robots.unreachable:
        result["outcome"], result["failure_class"] = "fetch_failed", "robots_unreachable"
        result["needs_review"].append("robots_unreachable")
        return
    top = ctx.get(m.url)
    profile["top"] = {"status": top.status, "final_url": top.final_url, "elapsed_ms": top.elapsed_ms, "redirects": top.redirects, "error_class": top.error_class}
    if top.error_class == "robots_disallowed":
        result["outcome"], result["failure_class"] = "robots_blocked", "robots_disallowed"
        return
    if not top.ok:
        result["outcome"], result["failure_class"] = "fetch_failed", top.error_class or "other"
        result["needs_review"].append(f"top_fetch_{result['failure_class']}")
        return
    final_host = base_host(top.final_url)
    if (urlsplit(top.final_url).hostname or "") != (urlsplit(m.url).hostname or ""):
        # リダイレクト先が別ホストなら、そちらのrobots.txtも確認する
        profile["robots_final_host"] = ctx.load_robots(top.final_url).to_dict()
        profile["redirected_to_other_host"] = True

    html = decode_bytes(top.body, top.content_type)
    soup = parse_html(html)
    if cfg.save_html_dir:
        _save_html(cfg, m, top.body)

    # 2. JS描画判定・ナビゲーション
    render = assess_rendering(html, soup)
    profile["rendering"] = render.to_dict()
    profile["fetch_method"] = "headless_fallback_needed" if render.needs_headless else "http"
    links = extract_links(soup, top.final_url, final_host)
    result["nav_links"] = [l.to_dict() for l in links if l.same_site][:400]
    result["menu_labels"] = find_menu_labels(soup)

    # 3. サイトマップ
    sm, tally = _sitemap(m, ctx, cfg, robots, top.final_url, final_host)
    profile["sitemap"] = sm

    # 4. CMS推定(リンクURL + サイトマップのサンプルURL)
    urls = [l.url for l in links if l.same_site] + (tally.sample if tally else [])
    profile["cms"] = detect_cms(html, soup, urls).to_dict()

    # 5. ハブ候補(トップのナビ → 上位候補ページ → その先のリンク、まで)
    decision, blocked = _find_hub(ctx, cfg, robots, links, tally, final_host)
    result["genre_entrypoints"] = [
        {"genre": hub.GENRE, "decision": decision.outcome, "provenance": "auto", "selected": decision.selected.to_dict() if decision.selected else None, "candidates": [c.to_dict() for c in decision.top], "blocked_by_robots": blocked[:20]}
    ]

    # 6. 総合判定(取得失敗と、取れたが判断できなかったものを区別する)
    outcome = decision.outcome
    if render.needs_headless and outcome != "hub_selected":
        outcome = "needs_headless"
        result["needs_review"].append("needs_headless")
    if outcome in ("hub_multiple", "hub_not_found"):
        result["needs_review"].append(outcome)
        result["ai_needed"] = not render.needs_headless
    result["outcome"] = outcome


def _visit(ctx: _Ctx, c: hub.Candidate, site_host: str):
    """候補ページを取得して施設名リンクの数などで再採点し、ページ内のリンクを返す。取れなければNone。"""
    page = ctx.get(c.url)
    if not page.ok or (page.content_type and "html" not in page.content_type.lower()):
        c.reasons.append(f"page_fetch_{page.error_class or page.status}")
        return None
    soup = parse_html(decode_bytes(page.body, page.content_type))
    links = extract_links(soup, page.final_url, site_host)
    n, head = hub.page_features(soup, links)
    hub.rescore_with_page(c, n, head)
    return links


def _find_hub(ctx: _Ctx, cfg: Config, robots: RobotsInfo, links, tally, site_host):
    cands = hub.candidates_from_links(links, "nav", 1)
    if tally:
        cands += hub.candidates_from_urls(tally.keyword_urls)
    # robotsで禁止されたパスは、後段でも取得できないため候補から外す(記録は残す)
    blocked = sorted({c.url for c in cands if not robots.can_fetch(c.url)})
    cands = [c for c in cands if c.url not in blocked]

    # 1段目: ナビの候補ページ(スポーツ語・施設を探す・教育/文化などの大分類)を取得
    children: list[hub.Candidate] = []
    visited: set[str] = set()
    for c in [c for c in cands if c.source == "nav" and c.score >= hub.FETCH_MIN][: cfg.d1_fetch]:
        visited.add(c.url)
        page_links = _visit(ctx, c, site_host)
        if page_links is not None:
            children += hub.candidates_from_links(page_links, "depth1_link", 2)[:10]
    children = [c for c in children if c.url not in blocked and robots.can_fetch(c.url)]

    # 2段目: 1段目のページで見つかった有望なリンクを、少数だけ取得して施設名リンクを確認
    seen: set[str] = set()
    for c in sorted(children, key=lambda c: -c.score):
        if len(seen) >= cfg.d2_fetch:
            break
        if c.url in visited or c.url in seen or c.score < cfg.d2_min_score:
            continue
        seen.add(c.url)
        _visit(ctx, c, site_host)
    return hub.decide(cands + children), blocked


def _sitemap(m, ctx, cfg, robots, top_url, site_host):
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(top_url))
    cands: list[tuple[str, str]] = []
    for u in robots.sitemaps:
        cands.append((u, "robots"))
    for u in (m.xml_sitemap_url, m.xml_sitemap_candidate_url):
        if u:
            cands.append((u, "master_csv"))
    cands.append((origin + "/sitemap.xml", "default_path"))
    seen, ordered = set(), []
    for u, src in cands:
        if u not in seen and is_same_site(u, site_host):
            seen.add(u)
            ordered.append((u, src))
    attempts = []
    info = {"found": False, "url": "", "source": "", "kind": "", "attempts": attempts}
    tally = None
    for url, src in ordered[: cfg.sitemap_attempts]:
        res = ctx.get(url)
        parsed = parse_sitemap(res.body) if res.ok else None
        attempts.append({"url": url, "source": src, "status": res.status, "error_class": res.error_class, "kind": parsed.kind if parsed else ""})
        if not parsed or parsed.kind == "invalid":
            continue
        tally = UrlTally()
        info.update(found=True, url=url, source=src, kind=parsed.kind)
        if parsed.kind == "urlset":
            tally.add(parsed.entries, hub.URL_HINTS)
        else:
            children = [loc for loc, _ in parsed.entries if is_same_site(loc, site_host)]
            fetched = 0
            for child in children[: cfg.sitemap_children]:
                cres = ctx.get(child)
                cp = parse_sitemap(cres.body) if cres.ok else None
                if cp and cp.kind == "urlset":
                    tally.add(cp.entries, hub.URL_HINTS)
                    fetched += 1
            info.update(children_total=len(children), children_fetched=fetched, truncated=len(children) > cfg.sitemap_children)
        info.update(tally.to_dict())
        break
    return info, tally


def _save_html(cfg: Config, m: Municipality, body: bytes) -> None:
    d = Path(cfg.save_html_dir) / cfg.route
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{m.code}.html.gz").write_bytes(gzip.compress(body))
