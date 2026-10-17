"""ヘッドレス取得(D-117)。ローカルのサーバーでJS描画のページを返し、描画後の内容を取れることを確かめる。playwright/chromium が無い環境では飛ばす。"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from localgov_crawler import survey as sv
from localgov_crawler.fetcher import Fetcher
from localgov_crawler.headless import HeadlessFetcher, HybridFetcher
from localgov_crawler.municipalities import Municipality

pytest.importorskip("playwright")

PAGES = {
    "/": "<html><head><title>JS市</title></head><body><div id=app></div><script src=/app.js></script></body></html>",
    "/sports/": "<html><head><title>スポーツ</title></head><body><div id=app></div><script src=/f.js></script></body></html>",
}
SCRIPTS = {
    "/app.js": "document.getElementById('app').innerHTML='<a href=\"/sports/\">スポーツ</a>';",
    "/f.js": "document.getElementById('app').innerHTML='<main><p>' + 'ご利用案内です。'.repeat(20) + '</p><p>多目的広場ではグラウンド・ゴルフができます。</p></main>';",
}


class Handler(BaseHTTPRequestHandler):
    hits: list = []

    def do_GET(self):
        Handler.hits.append(self.path)
        if self.path in PAGES:
            body, ctype = PAGES[self.path].encode("utf-8"), "text/html; charset=utf-8"
        elif self.path in SCRIPTS:
            body, ctype = SCRIPTS[self.path].encode("utf-8"), "application/javascript; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    Handler.hits = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _headless():
    h = HeadlessFetcher("test-agent", min_interval=0.05)
    r = h.get("about:blank")
    if r.error_class and "chrom" in (r.error_detail or "").lower():
        h.close()
        pytest.skip("chromium を起動できない環境")
    return h


def test_headless_returns_rendered_html(server):
    h = _headless()
    try:
        r = h.get(server + "/")
        assert r.ok and "スポーツ" in r.body.decode("utf-8") and 'href="/sports/"' in r.body.decode("utf-8")
        assert h.pages >= 1 and h.subrequests >= 2  # 文書とスクリプト。画像等は止める
    finally:
        h.close()


def test_survey_of_js_rendered_site_with_hybrid_fetcher(server):
    h = _headless()
    plain = Fetcher(min_interval=0)
    try:
        m = Municipality("29999", "JS市", "JS市", "29", "奈良県", "city", "municipality", "", server + "/", "", "")
        spec = sv.KeywordSpec("grandgolf", "グラウンドゴルフ", [__import__("re").compile(r"グラウ?ンド[\s・･\-ー]*ゴルフ")])
        stored = {"nav_links": [], "site_profile": {"rendering": {"needs_headless": True}}, "genre_entrypoints": []}
        out = sv.survey_municipality(m, stored, HybridFetcher(plain, h), spec, sv.SurveyConfig(route="t"))
        assert out["outcome"] == "surveyed" and out["seed_mode"] == "fallback" and out["found"]
        assert any(p["url"].endswith("/sports/") and p["hit"] for p in out["pages"])
        assert "/robots.txt" in Handler.hits  # robots.txt は通常の取得
    finally:
        plain.close()
        h.close()
