import json

from conftest import make_fetcher
from localgov_crawler import survey as sv
from localgov_crawler.municipalities import Municipality

M = Municipality("29999", "サンプル市", "サンプル市", "29", "奈良県", "city", "municipality", "", "https://www.city.example.jp/", "", "")
SPEC = sv.KeywordSpec("grandgolf", "グラウンドゴルフ", [__import__("re").compile(r"グラウ?ンド[\s・･\-ー]*ゴルフ")])
HTML = "text/html; charset=utf-8"


def page(title, body, nav=""):
    return (200, HTML, f"<html><head><title>{title}</title></head><body>{nav}<main>{body}</main></body></html>")


def result(cands=(), nav=()):
    return {
        "nav_links": [{"text": t, "url": u, "same_site": True, "is_pdf": False, "region": "nav"} for t, u in nav],
        "genre_entrypoints": [{"selected": None, "candidates": [dict(url=u, text=t, kind="sports_pure", score=20) for t, u in cands]}],
    }


def test_keyword_variants_after_nfkc():
    for t in ["グラウンドゴルフ", "グラウンド・ゴルフ", "グランドゴルフ", "ｸﾞﾗｳﾝﾄﾞｺﾞﾙﾌ", "グラウンド ゴルフ", "グランド･ゴルフ"]:
        assert SPEC.in_text(t), t
    assert not SPEC.in_text("パークゴルフ") and not SPEC.in_text("グラウンドとゴルフ場")


def test_page_text_drops_navigation_but_keeps_main():
    soup = sv.parse_html("<html><head><title>T</title></head><body><nav>グラウンドゴルフ</nav><div class='sidebar'>グラウンドゴルフ</div><main>本文</main></body></html>")
    title, body = sv.page_text(soup)
    assert title == "T" and "グラウンドゴルフ" not in body and "本文" in body


def test_survey_finds_word_in_facility_and_event_pages_and_skips_reservation():
    nav_html = '<nav><a href="/event/">スポーツ大会</a> グラウンドゴルフ</nav>'
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/sports/": page("スポーツ施設", '<a href="/f/1">中央運動場</a><a href="/f/2">市民体育館</a><a href="/yoyaku/">施設予約</a>', nav_html),
        "/f/1": page("中央運動場", "<p>グラウンド・ゴルフができます。</p>", nav_html),
        "/f/2": page("市民体育館", "<p>バスケットボール</p>", nav_html),
        "/event/": page("スポーツ大会", '<a href="/event/gg">グラウンドゴルフ大会</a><a href="/event/old">スポーツ大会 結果</a>'),
        "/event/gg": page("グラウンドゴルフ大会", "<p>第3回</p>"),
        "/yoyaku/": page("予約", "グラウンドゴルフ"),
    }
    r = result(cands=[("スポーツ施設", "https://www.city.example.jp/sports/")], nav=[("スポーツ大会", "https://www.city.example.jp/event/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "surveyed" and out["found"]
    by = {p["url"].replace("https://www.city.example.jp", "").strip("/").rsplit("/", 1)[-1]: p for p in out["pages"]}
    assert by["1"]["hit"] and by["1"]["role"] == "facility" and "グラウンド・ゴルフ" in by["1"]["snippets"][0]
    assert not by["2"]["hit"]  # ナビだけにあるワードは数えない
    assert by["gg"]["hit"] and by["gg"]["in_title"] and by["gg"]["role"] == "event"
    assert sorted(out["hit_roles"]) == ["event", "facility"]
    assert all("yoyaku" not in q["url"] for q in out["requests"])  # 予約システムには入らない
    assert by["sports"]["role"] == "listing" and not by["sports"]["hit"]


def test_robots_disallow_is_respected_and_budget_is_limited():
    routes = {
        "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /secret/\n"),
        "/sports/": page("スポーツ", "".join(f'<a href="/sports/{i}">運動場{i}</a>' for i in range(30)) + '<a href="/secret/x">体育館</a>'),
    }
    for i in range(30):
        routes[f"/sports/{i}"] = page(f"運動場{i}", "本文")
    r = result(cands=[("スポーツ", "https://www.city.example.jp/sports/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", max_pages=5))
    assert out["pages_fetched"] == 5 and out["stopped"] == "max_pages"
    assert all("/secret/" not in q["url"] for q in out["requests"])


def test_no_seed_and_unreachable_robots():
    assert sv.survey_municipality(M, {"nav_links": [], "genre_entrypoints": []}, make_fetcher({}), SPEC, sv.SurveyConfig())["outcome"] == "no_seed"
    r = result(cands=[("スポーツ", "https://www.city.example.jp/sports/")])
    out = sv.survey_municipality(M, r, make_fetcher({"/robots.txt": (503, "text/plain", "")}), SPEC, sv.SurveyConfig(retry_wait=0))
    assert out["outcome"] == "fetch_failed" and out["failure_class"] == "robots_unreachable" and not out["pages"]


def test_summary_rows(tmp_path):
    routes = {"/robots.txt": (404, "text/plain", ""), "/sports/": page("スポーツ", "グランドゴルフ場あり")}
    r = result(cands=[("スポーツ", "https://www.city.example.jp/sports/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t"))
    sv.write_survey(tmp_path, out, "29")
    rows = sv.survey_rows(sv.load_surveys(tmp_path, "grandgolf", "t"))
    assert rows[0]["found"] and rows[0]["first_hit_role"] == "listing" and "グランドゴルフ" in rows[0]["first_hit_snippet"]
    assert "ワードがあった: 1" in sv.summary_markdown(rows, "grandgolf")
