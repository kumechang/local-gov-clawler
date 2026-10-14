import time

import httpx

from localgov_crawler.fetcher import Fetcher, classify_exception, classify_http_status


def test_status_classes():
    assert classify_http_status(403) == "http_403"
    assert classify_http_status(404) == "http_404"
    assert classify_http_status(429) == "http_429"
    assert classify_http_status(418) == "http_4xx"
    assert classify_http_status(503) == "http_5xx"
    assert classify_http_status(200) == ""


def test_exception_classes():
    assert classify_exception(httpx.ConnectTimeout("t")) == "timeout"
    assert classify_exception(httpx.ConnectError("[Errno -2] Name or service not known")) == "dns"
    assert classify_exception(httpx.ConnectError("Connection refused")) == "conn_refused"
    assert classify_exception(httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED]")) == "tls"
    assert classify_exception(httpx.ConnectError("Connection reset by peer")) == "conn_reset"
    assert classify_exception(httpx.ProxyError("x")) == "proxy_error"


def test_fetch_ok_truncate_and_error():
    def handler(req):
        if req.url.path == "/big":
            return httpx.Response(200, content=b"x" * 1000)
        if req.url.path == "/boom":
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(403)

    f = Fetcher(min_interval=0, max_bytes=100, transport=httpx.MockTransport(handler))
    big = f.get("https://a.jp/big")
    assert big.ok and big.truncated and len(big.body) == 100
    assert f.get("https://a.jp/boom").error_class == "conn_refused"
    r = f.get("https://a.jp/x")
    assert not r.ok and r.error_class == "http_403" and r.status == 403


def test_per_host_rate_limit_and_crawl_delay():
    f = Fetcher(min_interval=0.2, transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
    t = time.monotonic()
    f.get("https://a.jp/1"); f.get("https://a.jp/2")
    assert time.monotonic() - t >= 0.2
    t = time.monotonic()
    f.get("https://b.jp/1")  # 別ホストは待たない
    assert time.monotonic() - t < 0.15
    f.set_host_delay("a.jp", 0.4)
    t = time.monotonic()
    f.get("https://a.jp/3")
    assert time.monotonic() - t >= 0.15


def test_user_agent_has_contact():
    f = Fetcher(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=r.headers["user-agent"])))
    assert "https://github.com/" in f.get("https://a.jp/").body.decode()
