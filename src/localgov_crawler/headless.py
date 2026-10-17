"""JS描画のサイト用のフォールバック(handoff §2: 本文が空・JS描画のページのみヘッドレスブラウザを使う)。
通常の取得(httpx)と同じ `get(url)` を持ち、描画後のHTMLを返す。robots.txt は通常の取得で読む。
ブラウザはページを開くときにスクリプト等を追加で読み込むので、画像・フォント・スタイル・メディアは止め、残りも
同じホストへ1秒に1回以下になるよう間隔を空ける(取得のルール: 1ホスト1リクエスト/秒以下)。"""
from __future__ import annotations

import glob
import os
import threading
import time
from urllib.parse import urlsplit

from .fetcher import FetchResult, Fetcher, classify_http_status

BLOCKED_TYPES = {"image", "media", "font", "stylesheet", "other", "ping", "websocket", "eventsource", "manifest", "texttrack"}


def find_chromium() -> str | None:
    """環境変数 CHROMIUM_PATH、なければ PLAYWRIGHT_BROWSERS_PATH 配下の chromium。見つからなければ Playwright の標準に任せる。"""
    path = os.environ.get("CHROMIUM_PATH")
    if path:
        return path
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base:
        found = sorted(glob.glob(os.path.join(base, "chromium-*", "chrome-linux", "chrome")))
        if found:
            return found[-1]
    return None


class HeadlessFetcher:
    def __init__(self, user_agent: str, min_interval: float = 1.0, timeout: float = 30.0, max_bytes: int = 5_000_000, chromium_path: str | None = None):
        self.user_agent, self.min_interval, self.timeout, self.max_bytes = user_agent, min_interval, timeout, max_bytes
        self.chromium_path = chromium_path or find_chromium()
        self.used_proxy = False
        self.pages = 0
        self.subrequests = 0
        self._host_delay: dict[str, float] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self._pw = self._browser = self._ctx = self._page = None

    def set_host_delay(self, host: str, seconds: float) -> None:
        self._host_delay[host] = seconds

    def _wait(self, host: str) -> None:
        interval = max(self.min_interval, self._host_delay.get(host, 0.0))
        with self._lock:
            now = time.monotonic()
            wait = self._last.get(host, 0.0) + interval - now
            self._last[host] = now + max(wait, 0.0)
        if wait > 0:
            time.sleep(wait)

    def _route(self, route) -> None:
        req = route.request
        if req.resource_type in BLOCKED_TYPES:
            route.abort()
            return
        self._wait((urlsplit(req.url).hostname or "").lower())
        self.subrequests += 1
        route.continue_()

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright  # 重い依存なので、使うときだけ読み込む

        self._pw = sync_playwright().start()
        kwargs: dict = {"args": ["--no-sandbox"]}
        if self.chromium_path:
            kwargs["executable_path"] = self.chromium_path
        self._browser = self._pw.chromium.launch(**kwargs)
        self._ctx = self._browser.new_context(user_agent=self.user_agent, locale="ja-JP")
        self._ctx.route("**/*", self._route)
        self._page = self._ctx.new_page()

    def get(self, url: str) -> FetchResult:
        res = FetchResult(url=url, final_url=url)
        start = time.monotonic()
        try:
            if self._page is None:
                self._start()
            resp = self._page.goto(url, wait_until="load", timeout=int(self.timeout * 1000))
            try:
                self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # 通信が落ち着かないサイトは、読み込めた分で進める
            self.pages += 1
            res.status = resp.status if resp is not None else None
            res.final_url = self._page.url
            ctype = (resp.headers.get("content-type", "") if resp is not None else "") or "text/html"
            if "html" in ctype.lower():
                res.body = self._page.content().encode("utf-8")[: self.max_bytes]
                res.content_type = "text/html; charset=utf-8"
            else:
                res.content_type = ctype
            res.error_class = classify_http_status(res.status) if res.status is not None else "other"
            if res.error_class:
                res.error_detail = f"HTTP {res.status}"
        except Exception as exc:  # 取得失敗は例外にせず結果として記録する
            res.error_class = "timeout" if "Timeout" in type(exc).__name__ else "other"
            res.error_detail = f"{type(exc).__name__}: {exc}"[:300]
        res.elapsed_ms = int((time.monotonic() - start) * 1000)
        return res

    def close(self) -> None:
        for obj in (self._ctx, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._ctx = self._page = None


class HybridFetcher:
    """robots.txt は通常の取得、ページはヘッドレスで取得する。"""

    def __init__(self, plain: Fetcher, headless: HeadlessFetcher):
        self.plain, self.headless = plain, headless
        self.used_proxy = plain.used_proxy

    def get(self, url: str) -> FetchResult:
        if urlsplit(url).path.endswith("/robots.txt"):
            return self.plain.get(url)
        return self.headless.get(url)

    def set_host_delay(self, host: str, seconds: float) -> None:
        self.plain.set_host_delay(host, seconds)
        self.headless.set_host_delay(host, seconds)
