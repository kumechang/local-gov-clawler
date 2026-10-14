import httpx

from conftest import fixture_text, make_fetcher
from localgov_crawler import store
from localgov_crawler.municipalities import Municipality
from localgov_crawler.pipeline import Config, analyze

M = Municipality("29999", "サンプル市", "サンプル市", "29", "奈良県", "city", "municipality", "", "https://www.city.example.jp/", "", "")


def test_hub_selected(city_routes):
    r = analyze(M, make_fetcher(city_routes), Config(route="test"))
    assert r["outcome"] == "hub_selected" and not r["ai_needed"]
    sel = r["genre_entrypoints"][0]["selected"]
    assert sel["url"].endswith("/sports/shisetsu.html") and sel["facility_link_count"] == 4
    p = r["site_profile"]
    assert p["sitemap"]["found"] and p["sitemap"]["url_count"] == 2 and p["sitemap"]["source"] == "robots"
    assert p["cms"]["family"] == "wordpress"
    assert p["robots"]["available"] and p["used_proxy"] is False
    assert r["menu_labels"] and r["nav_links"]
    assert r["run"]["request_count"] == len(r["requests"]) <= 30
    # 大会募集のニュースリンクは入口候補にならない
    assert all("news" not in c["url"] for c in r["genre_entrypoints"][0]["candidates"])


def test_robots_disallow_prevents_fetch_and_excludes_candidate(city_routes):
    city_routes["/robots.txt"] = (200, "text/plain", "User-agent: *\nDisallow: /sports/\n")
    r = analyze(M, make_fetcher(city_routes), Config())
    assert all("/sports/" not in q["url"] for q in r["requests"])
    ge = r["genre_entrypoints"][0]
    assert ge["blocked_by_robots"] == ["https://www.city.example.jp/sports/shisetsu.html"]
    assert r["outcome"] == "hub_not_found"


def test_top_page_forbidden_is_fetch_failed_not_ai():
    r = analyze(M, make_fetcher({"/": httpx.Response(403, text="forbidden")}), Config())
    assert r["outcome"] == "fetch_failed" and r["failure_class"] == "http_403" and not r["ai_needed"]


def test_robots_5xx_is_failure_with_no_page_requested():
    r = analyze(M, make_fetcher({"/robots.txt": (503, "text/plain", ""), "/": (200, "text/html", "<html></html>")}), Config(retry_wait=0))
    assert r["outcome"] == "fetch_failed" and r["failure_class"] == "robots_unreachable"
    assert all(not q["url"].endswith("/") or q["url"].endswith("robots.txt") for q in r["requests"])
    assert [q.get("retry") for q in r["requests"]] == [None, True]  # robotsの5xxは1回だけ再試行


def test_no_sports_link_goes_to_ai_queue():
    html = "<html><head><title>x</title></head><body>" + "".join(f'<a href="/p{i}.html">メニュー{i}</a>' for i in range(30)) + "本文" * 200 + "</body></html>"
    r = analyze(M, make_fetcher({"/": (200, "text/html; charset=utf-8", html)}), Config())
    assert r["outcome"] == "hub_not_found" and r["ai_needed"]


def test_js_shell_is_needs_headless():
    html = '<html><body><div id="app"></div><script src="/app.js"></script></body></html>'
    r = analyze(M, make_fetcher({"/": (200, "text/html", html)}), Config())
    assert r["outcome"] == "needs_headless" and not r["ai_needed"]
    assert r["site_profile"]["fetch_method"] == "headless_fallback_needed"


def test_sitemap_index_and_budget(city_routes):
    city_routes["/sitemap.xml"] = (200, "application/xml", '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://www.city.example.jp/sm1.xml</loc></sitemap></sitemapindex>')
    city_routes["/sm1.xml"] = (200, "application/xml", '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://www.city.example.jp/a</loc></url></urlset>')
    r = analyze(M, make_fetcher(city_routes), Config())
    sm = r["site_profile"]["sitemap"]
    assert sm["kind"] == "index" and sm["children_fetched"] == 1 and sm["url_count"] == 1
    tight = analyze(M, make_fetcher(city_routes), Config(max_requests=3))
    assert tight["run"]["request_count"] == 3


def test_no_url():
    r = analyze(Municipality("1", "x", "x", "01", "北海道", "city", "municipality", "", "", "", ""), make_fetcher({}), Config())
    assert r["outcome"] == "no_url"


def test_store_roundtrip_summary_and_evaluate(tmp_path, city_routes):
    r = analyze(M, make_fetcher(city_routes), Config(route="test"))
    bad = analyze(Municipality("29998", "失敗町", "失敗町", "29", "奈良県", "town", "municipality", "", "https://www.town.x.jp/", "", ""),
                  make_fetcher({"/": httpx.Response(403)}), Config(route="test"))
    store.write_result(tmp_path, r, "29")
    store.write_result(tmp_path, bad, "29")
    results = store.load_results(tmp_path, "test")
    assert len(results) == 2
    s = store.summarize(results)
    assert s["total"] == 2 and s["fetch_failure_rate"] == 0.5 and s["failure_classes"] == {"http_403": 1}
    assert s["hub_selected_rate"] == 0.5 and s["municipalities_failed"] == ["29998"]
    truth = tmp_path / "truth.csv"
    truth.write_text("municipality_code,hub_url,notes\n29999,https://www.city.example.jp/sports/shisetsu.html/,\n29998,https://www.town.x.jp/sports/,\n", encoding="utf-8")
    ev = store.evaluate(results, truth)
    assert ev["truth_count"] == 2 and ev["reached"] == 1 and ev["reach_rate"] == 0.5
    store.build_db(tmp_path, "test", [M], tmp_path / "x.sqlite")
    import sqlite3
    con = sqlite3.connect(tmp_path / "x.sqlite")
    assert con.execute("select status from municipalities").fetchone() == ("hub_selected",)
    assert con.execute("select cms_family from site_profiles").fetchone() == ("wordpress",)


# --- 奈良県パイロット第1回で見つかった失敗パターンの再現(docs/reports/pilot-nara-run1.md) ---

HTML = "text/html; charset=utf-8"


def page(body: str, title: str = "x") -> str:
    """本文とリンクが十分ある(JS描画と誤判定されない)ページを作る。"""
    filler = "".join(f'<a href="/other/{i}.html">各種手続き{i}</a>' for i in range(12)) + "お知らせを掲載しています。" * 30
    return f"<html><head><title>{title}</title></head><body>{body}{filler}</body></html>"


FACILITIES = '<a href="/f/1.html">市民体育館</a><a href="/f/2.html">中央グラウンド</a><a href="/f/3.html">市民プール</a><a href="/f/4.html">テニスコート</a>'


def test_explore_link_leads_to_facility_list():
    """「施設を探す」だけがあるトップ(五條市・田原本町型)。先のページに施設名リンクが並ぶ。"""
    routes = {
        "/": (200, HTML, page('<nav><a href="/shisetsu/">施設を探す</a></nav>')),
        "/shisetsu/": (200, HTML, page(FACILITIES, "施設を探す")),
    }
    r = analyze(M, make_fetcher(routes), Config(retry_wait=0))
    sel = r["genre_entrypoints"][0]["selected"]
    assert r["outcome"] == "hub_selected" and sel["url"].endswith("/shisetsu/") and sel["facility_link_count"] == 4


def test_two_level_category_to_sports_page():
    """トップ「教育・文化・スポーツ」→「スポーツ・体育」→施設一覧(桜井市型)。2段目を取得して確定する。"""
    routes = {
        "/": (200, HTML, page('<nav><a href="/life/16/">教育・文化・スポーツ</a></nav>')),
        "/life/16/": (200, HTML, page('<a href="/life/16/taiiku/">スポーツ・体育</a><a href="/life/16/bunka/">文化財</a>')),
        "/life/16/taiiku/": (200, HTML, page(FACILITIES, "スポーツ・体育")),
    }
    r = analyze(M, make_fetcher(routes), Config(retry_wait=0))
    sel = r["genre_entrypoints"][0]["selected"]
    assert r["outcome"] == "hub_selected" and sel["url"].endswith("/life/16/taiiku/") and sel["depth"] == 2 and sel["fetched"]


def test_category_without_facility_links_is_not_a_hub():
    """「観光・文化・スポーツ」の大分類ページに施設リンクが無ければ確定しない(大和郡山市型)。"""
    routes = {
        "/": (200, HTML, page('<nav><a href="/kanko/">観光・文化・スポーツ</a></nav>')),
        "/kanko/": (200, HTML, page('<a href="/kanko/rekishi/">歴史</a>')),
    }
    r = analyze(M, make_fetcher(routes), Config(retry_wait=0))
    assert r["outcome"] == "hub_not_found" and r["ai_needed"]


def test_news_titles_are_not_hubs():
    """お知らせ記事のタイトルは高得点にならない(天理市・斑鳩町・御所市型)。"""
    news = "".join(f'<a href="/n/{i}.html">{t}</a>' for i, t in enumerate(
        ["天理市体育施設指定管理者募集", "社会体育施設の熱中症対策について", "学校体育施設利用手続きの改正について", "御所スポーツフェスティバル2026"]))
    r = analyze(M, make_fetcher({"/": (200, HTML, page(news))}), Config(retry_wait=0))
    assert r["outcome"] == "hub_not_found"
    assert all("/n/" not in q["url"] for q in r["requests"])  # お知らせ記事は取得もしない


def test_facility_page_does_not_beat_list_page():
    """一覧ページ(深さ1)の配下の個別施設ページ(深さ2、高得点)が競合しない(葛城市型)。"""
    routes = {
        "/": (200, HTML, page('<nav><a href="/kbs/">観光・文化・スポーツ</a></nav>')),
        "/kbs/": (200, HTML, page('<a href="/kbs/s/5796.html">屋敷山公園内 体育施設情報</a>' + FACILITIES)),
        "/kbs/s/5796.html": (200, HTML, page("詳細")),
    }
    r = analyze(M, make_fetcher(routes), Config(retry_wait=0))
    assert r["outcome"] == "hub_selected"
    assert r["genre_entrypoints"][0]["selected"]["url"].endswith("/kbs/")


def test_image_only_links_are_kept_and_not_headless():
    """リンクが画像だけの静的ポータル(山添村型)。JS描画と誤判定せずリンクを拾う。"""
    html = '<html><head><title>村</title></head><body><a href="/life"><img src="images/kurashi.png"></a><a href="/kanko"><img src="images/kanko.png" alt="観光"></a><img src="a.jpg"><img src="b.jpg"></body></html>'
    r = analyze(M, make_fetcher({"/": (200, HTML, html)}), Config(retry_wait=0))
    assert r["outcome"] != "needs_headless"
    kinds = {l["text"]: l["text_kind"] for l in r["nav_links"]}
    assert kinds == {"kurashi": "img_src", "観光": "img_alt"}


def test_retry_once_on_transient_errors():
    """候補ページの408(平群町型)は1回だけ再試行する。2回目で取れれば使う。"""
    calls = {"n": 0}

    def handler(request):
        if request.url.path == "/":
            return httpx.Response(200, headers={"content-type": HTML}, text=page('<nav><a href="/life/1/">スポーツ情報</a></nav>'))
        if request.url.path == "/life/1/":
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(408, text="timeout")
            return httpx.Response(200, headers={"content-type": HTML}, text=page(FACILITIES))
        return httpx.Response(404)

    from localgov_crawler.fetcher import Fetcher

    f = Fetcher(min_interval=0, transport=httpx.MockTransport(handler))
    r = analyze(M, f, Config(retry_wait=0))
    statuses = [(q["status"], q.get("retry")) for q in r["requests"] if q["url"].endswith("/life/1/")]
    assert statuses == [(408, None), (200, True)]
    assert r["outcome"] == "hub_selected"


def test_retry_after_longer_than_limit_is_not_retried():
    def handler(request):
        if request.url.path == "/":
            return httpx.Response(429, headers={"retry-after": "120"})
        return httpx.Response(404)

    from localgov_crawler.fetcher import Fetcher

    r = analyze(M, Fetcher(min_interval=0, transport=httpx.MockTransport(handler)), Config(retry_wait=0))
    assert r["failure_class"] == "http_429"
    assert sum(1 for q in r["requests"] if not q["url"].endswith("robots.txt")) == 1


def test_html_sitemap_page_is_followed_but_never_selected():
    """トップのナビが「サイトマップ」「くらし」だけの小さな村(黒滝村・東吉野村型)。サイトマップページ経由で候補を拾う。"""
    routes = {
        "/": (200, HTML, page('<nav><a href="/sitemap/">サイトマップ</a><a href="/life/">暮らし</a></nav>')),
        "/sitemap/": (200, HTML, page('<a href="/life/sports/">スポーツ施設</a>' + FACILITIES)),  # 施設名リンクが4つあってもサイトマップ自体は採用しない
        "/life/": (200, HTML, page("<a href=\"/life/news/\">新着</a>")),
        "/life/sports/": (200, HTML, page(FACILITIES, "スポーツ施設")),
    }
    r = analyze(M, make_fetcher(routes), Config(retry_wait=0))
    sel = r["genre_entrypoints"][0]["selected"]
    assert r["outcome"] == "hub_selected" and sel["url"].endswith("/life/sports/") and sel["depth"] == 2
    assert all(not c["viable"] for c in r["genre_entrypoints"][0]["candidates"] if c["url"].endswith(("/sitemap/", "/life/")))
