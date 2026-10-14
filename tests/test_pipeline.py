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
    assert r["run"]["request_count"] == len(r["requests"]) <= 25
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
    r = analyze(M, make_fetcher({"/robots.txt": (503, "text/plain", ""), "/": (200, "text/html", "<html></html>")}), Config())
    assert r["outcome"] == "fetch_failed" and r["failure_class"] == "robots_unreachable"
    assert all(not q["url"].endswith("/") or q["url"].endswith("robots.txt") for q in r["requests"])


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
