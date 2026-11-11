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


def test_redirect_hops_are_paced_and_followed():
    """リダイレクトも1リクエストなので、間隔をあけてたどる(自動追従は間隔なしに連続して送ってしまった。D-159)。"""
    times = []

    def handler(request):
        times.append(time.monotonic())
        if request.url.path == "/a":
            return httpx.Response(301, headers={"location": "/b"})
        if request.url.path == "/b":
            return httpx.Response(302, headers={"location": "https://www.example.jp/c"})
        return httpx.Response(200, text="ok")

    f = Fetcher(min_interval=0.2, transport=httpx.MockTransport(handler))
    res = f.get("https://www.example.jp/a")
    assert res.ok and res.final_url == "https://www.example.jp/c" and res.redirects == 2 and res.body == b"ok"
    assert len(times) == 3 and all(b - a >= 0.19 for a, b in zip(times, times[1:]))


def test_too_many_redirects_is_classified():
    f = Fetcher(min_interval=0, transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "/loop"})))
    res = f.get("https://www.example.jp/loop")
    assert res.error_class == "too_many_redirects" and res.redirects == 5


def test_interval_is_measured_from_the_actual_start(monkeypatch):
    """スリープの起床が遅れても、次のリクエストとの間隔は実際の開始時刻から測る(以前は予約した時刻から測り、間隔が1秒を切ることがあった)。"""
    clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    def late_sleep(sec):
        clock[0] += sec + 0.3  # 0.3秒遅れて起きる

    monkeypatch.setattr(time, "sleep", late_sleep)
    f = Fetcher(min_interval=1.0, transport=httpx.MockTransport(lambda r: httpx.Response(200, text="ok")))
    starts = []
    for _ in range(4):
        f._wait("a.jp")
        starts.append(clock[0])
        clock[0] += 0.1  # リクエストにかかる時間
    assert all(b - a >= 1.0 for a, b in zip(starts, starts[1:]))
