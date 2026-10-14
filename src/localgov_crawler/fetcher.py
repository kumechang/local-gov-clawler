"""HTTP取得。ホスト単位のレート制限、サイズ上限、失敗原因の分類を担う。"""
from __future__ import annotations

import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

PRODUCT_TOKEN = "local-gov-crawler"
DEFAULT_CONTACT = "https://github.com/kumechang/local-gov-clawler"


def build_user_agent(contact: str = DEFAULT_CONTACT) -> str:
    return f"{PRODUCT_TOKEN}/0.1 (research; +{contact})"


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status: int | None = None
    content_type: str = ""
    body: bytes = b""
    truncated: bool = False
    elapsed_ms: int = 0
    error_class: str = ""  # 空なら取得できた(HTTPエラー含む場合はhttp_*が入る)
    error_detail: str = ""
    redirects: int = 0
    etag: str = ""
    last_modified: str = ""
    retry_after: float | None = None  # 秒。Retry-Afterが秒数のときだけ

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300 and not self.error_class

    def log_entry(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "error_class": self.error_class,
            "elapsed_ms": self.elapsed_ms,
            "bytes": len(self.body),
        }


def classify_http_status(status: int) -> str:
    if status == 403:
        return "http_403"
    if status == 408:
        return "http_408"
    if status == 429:
        return "http_429"
    if status in (404, 410):
        return "http_404"
    if 400 <= status < 500:
        return "http_4xx"
    if status >= 500:
        return "http_5xx"
    return ""


def classify_exception(exc: BaseException) -> str:
    """失敗の切り分け: IP制限・bot対策・サイト不安定をおおむね区別するための分類。"""
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return "timeout"
    if isinstance(exc, httpx.ProxyError):
        return "proxy_error"
    if isinstance(exc, httpx.TooManyRedirects):
        return "too_many_redirects"
    text = f"{type(exc).__name__} {exc}".lower()
    cause = exc.__cause__ or exc.__context__
    if isinstance(cause, socket.gaierror) or "name or service not known" in text or "nodename" in text or "getaddrinfo" in text:
        return "dns"
    if isinstance(cause, ssl.SSLError) or "ssl" in text or "certificate" in text:
        return "tls"
    if "refused" in text:
        return "conn_refused"
    if "reset" in text:
        return "conn_reset"
    if isinstance(exc, (httpx.ReadError, httpx.RemoteProtocolError)):
        return "conn_reset"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    return "other"


class Fetcher:
    def __init__(
        self,
        user_agent: str | None = None,
        proxy: str | None = None,
        timeout: float = 20.0,
        min_interval: float = 1.0,
        max_bytes: int = 5_000_000,
        transport: httpx.BaseTransport | None = None,
    ):
        self.user_agent = user_agent or build_user_agent()
        self.min_interval = min_interval
        self.max_bytes = max_bytes
        self.used_proxy = bool(proxy)
        self._host_delay: dict[str, float] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        # trust_env=False: 環境変数のプロキシを暗黙に使わない(直接/プロキシの比較を明確にするため)
        self._client = httpx.Client(
            headers={"User-Agent": self.user_agent, "Accept-Language": "ja,en;q=0.5"},
            timeout=timeout,
            follow_redirects=True,
            max_redirects=5,
            proxy=proxy,
            trust_env=False,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def set_host_delay(self, host: str, seconds: float) -> None:
        with self._lock:
            self._host_delay[host] = seconds

    def _wait(self, host: str) -> None:
        interval = max(self.min_interval, self._host_delay.get(host, 0.0))
        with self._lock:
            now = time.monotonic()
            wait = self._last.get(host, 0.0) + interval - now
            self._last[host] = now + max(wait, 0.0)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str) -> FetchResult:
        host = (urlsplit(url).hostname or "").lower()
        res = FetchResult(url=url, final_url=url)
        self._wait(host)
        start = time.monotonic()
        try:
            with self._client.stream("GET", url) as r:
                res.status = r.status_code
                res.final_url = str(r.url)
                res.redirects = len(r.history)
                res.content_type = r.headers.get("content-type", "")
                res.etag = r.headers.get("etag", "")
                res.last_modified = r.headers.get("last-modified", "")
                ra = r.headers.get("retry-after", "")
                res.retry_after = float(ra) if ra.strip().isdigit() else None
                chunks, size = [], 0
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        res.truncated = True
                        chunks.append(chunk[: len(chunk) - (size - self.max_bytes)])
                        break
                    chunks.append(chunk)
                res.body = b"".join(chunks)
            res.error_class = classify_http_status(res.status)
            if res.error_class:
                res.error_detail = f"HTTP {res.status}"
        except Exception as exc:  # 取得失敗は例外にせず結果として記録する
            res.error_class = classify_exception(exc)
            res.error_detail = f"{type(exc).__name__}: {exc}"[:300]
        res.elapsed_ms = int((time.monotonic() - start) * 1000)
        return res
