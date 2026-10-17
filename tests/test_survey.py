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
    out0 = sv.survey_municipality(M, {"nav_links": [], "genre_entrypoints": []}, make_fetcher({}), SPEC, sv.SurveyConfig())
    assert out0["outcome"] == "fetch_failed" and out0["failure_class"].startswith("top_fetch_")  # 入口が無く、トップも取れない
    plain = {"/robots.txt": (404, "text/plain", ""), "/": page("トップ", '<a href="/news/">お知らせ</a>')}
    assert sv.survey_municipality(M, {"nav_links": [], "genre_entrypoints": []}, make_fetcher(plain), SPEC, sv.SurveyConfig())["outcome"] == "no_seed"
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


def test_classify_page_by_content():
    c = sv.classify_page
    assert c("碧南市レクリエーション協会/碧南市") == "organization"
    assert c("各種スポーツ関連表彰の受賞者、受賞団体の紹介") == "organization"
    assert c("第33回町民グラウンドゴルフ大会/大治町") == "event"
    assert c("市スポーツ大会・教室|弥富市公式ホームページ") == "event"
    assert c("西尾市吉良グラウンド・ゴルフ場|西尾市公式ウェブサイト") == "facility"
    assert c("桜ヶ丘公園(グラウンド)/豊川市") == "facility"
    assert c("公園使用の許可 - 尾張旭市公式ホームページ(公園農政課)") == "facility"  # 『公園』を含む。手続きの種類は今後の分類の課題
    assert c("お問い合わせ") == "other"


def test_priority_fetches_facility_and_keyword_links_before_event_pages_under_the_cap():
    events = "".join(f'<a href="/ev/{i}">スポーツ大会{i}</a>' for i in range(40))
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/sports/": page("スポーツ", '<a href="/event/">スポーツ大会</a><a href="/f/gg">西部グラウンドゴルフ場</a>'),
        "/event/": page("スポーツ大会", events),
        "/f/gg": page("西部グラウンドゴルフ場", "施設"),
    }
    for i in range(40):
        routes[f"/ev/{i}"] = page(f"スポーツ大会{i}", "本文")
    r = result(cands=[("スポーツ", "https://www.city.example.jp/sports/")], nav=[("スポーツ大会", "https://www.city.example.jp/event/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", max_pages=4))
    urls = [p["url"].rsplit("/", 1)[-1] for p in out["pages"]]
    assert "gg" in urls and urls.index("gg") <= 2  # ワードを含むリンクが先
    assert out["pages"][urls.index("gg")]["kind"] == "facility" and out["found"]


def test_event_pages_are_capped_separately():
    events = "".join(f'<a href="/ev/{i}">スポーツ大会{i}</a>' for i in range(30))
    routes = {"/robots.txt": (404, "text/plain", ""), "/event/": page("スポーツ大会", events)}
    for i in range(30):
        routes[f"/ev/{i}"] = page(f"スポーツ大会{i}", "本文")
    r = result(nav=[("スポーツ大会", "https://www.city.example.jp/event/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", max_event_pages=5))
    assert out["pages_fetched"] == 5


def test_pdf_link_only_is_reported_separately():
    routes = {"/robots.txt": (404, "text/plain", ""), "/sports/": page("スポーツ", "本文", '<nav><a href="/a.pdf">グラウンドゴルフ大会要項</a></nav>')}  # ナビのPDFリンクは本文に数えない
    out = sv.survey_municipality(M, result(cands=[("スポーツ", "https://www.city.example.jp/sports/")]), make_fetcher(routes), SPEC, sv.SurveyConfig(route="t"))
    assert not out["found"] and out["pdf_link_found"]
    rows = sv.survey_rows([out])
    assert rows[0]["pdf_link_found"] and "PDFのリンク文言だけにあった: 1" in sv.summary_markdown(rows, "grandgolf")


def _pt(html):
    return sv.page_text(sv.parse_html(html))


def test_page_text_keeps_content_inside_wrappers_with_chrome_like_class_names():  # 実サイトで本文が空になっていた原因(D-111)
    long = "本文です。" * 30
    html = f'<html><body class="has-sidebar page-header"><div id="wrapper" class="menu-open header-fixed"><div class="sidebar">ナビ語</div><div class="content">グラウンドゴルフ {long}</div></div></body></html>'
    title, body = _pt(html)
    assert "グラウンドゴルフ" in body and "ナビ語" not in body and len(body) > 100


def test_page_text_form_wrapper_and_main_container():
    long = "本文です。" * 30
    html = f'<html><body><form id="aspnetForm"><div id="gnav">グランドゴルフ(メニュー)</div><div id="contents"><p>{long}</p><p>グラウンド・ゴルフ場</p></div></form></body></html>'
    _, body = _pt(html)
    assert "グラウンド・ゴルフ場" in body and "メニュー" not in body


def test_site_wide_boilerplate_hits_are_not_counted():
    banner = '<div class="banner">グラウンドゴルフ教室のお知らせ</div>'
    routes = {"/robots.txt": (404, "text/plain", ""), "/sports/": page("スポーツ", "".join(f'<a href="/f/{i}">運動場{i}</a>' for i in range(6)) + banner)}
    for i in range(6):
        routes[f"/f/{i}"] = page(f"運動場{i}", f"<p>本文{i}</p>" + banner)
    routes["/f/3"] = page("運動場3", "<p>グラウンドゴルフ場があります</p>" + banner)
    out = sv.survey_municipality(M, result(cands=[("スポーツ", "https://www.city.example.jp/sports/")]), make_fetcher(routes), SPEC, sv.SurveyConfig(route="t"))
    hits = [p["url"].rsplit("/", 1)[-1] for p in out["pages"] if p["hit"]]
    assert hits == ["3"]  # 全ページ共通のバナーは数えない。固有の記載は数える


def test_negated_mentions_are_not_hits():  # 豊山町: 『グラウンド・ゴルフではご利用いただけません』(D-113)
    assert sv.is_negated("ゲートボール専用です。グラウンド・ゴルフではご利用いただけません。", len("ゲートボール専用です。グラウンド・ゴルフ"))
    assert not sv.is_negated("グラウンド・ゴルフにご利用いただけます。ゲートボールは不可。", len("グラウンド・ゴルフ"))  # 次の文の否定は無関係
    routes = {"/robots.txt": (404, "text/plain", ""), "/sports/": page("スポーツ", '<a href="/f/1">ゲートボール場</a><a href="/f/2">多目的広場</a>'),
              "/f/1": page("ゲートボール場", "<p>ゲートボール専用です。グラウンド・ゴルフではご利用いただけません。</p>"),
              "/f/2": page("多目的広場", "<p>グラウンド・ゴルフにご利用いただけます。</p>")}
    out = sv.survey_municipality(M, result(cands=[("スポーツ", "https://www.city.example.jp/sports/")]), make_fetcher(routes), SPEC, sv.SurveyConfig(route="t"))
    by = {p["url"].rsplit("/", 1)[-1]: p for p in out["pages"]}
    assert not by["1"]["hit"] and by["1"]["negated"] == 1 and by["2"]["hit"]


def test_negation_only_counts_on_the_same_line_as_the_word():  # D-116: 禁止されているのは他のスポーツ
    html = '<ul><li>グラウンド・ゴルフ</li><li>ゲートボール</li><li>野球・サッカーは使用禁止です</li></ul><p>多目的広場は、グラウンドゴルフ、ゲートボールに利用できます。</p><table><tr><th>利用種目</th><td>グラウンドゴルフ</td></tr><tr><th>注意</th><td>ゴルフ練習は禁止</td></tr></table>'
    title, body = _pt(f"<html><head><title>T</title></head><body><main>{html}{'<p>本文です。</p>' * 20}</main></body></html>")
    assert len(SPEC.find_affirmative(body)) == 3  # 3か所とも、同じ行に否定は無い
    assert len(SPEC.find_lines(body)) == 3
    one = "<p>ゲートボール専用です。グラウンド・ゴルフではご利用いただけません。</p>"
    _, body2 = _pt(f"<html><body><main>{one}{'<p>本文です。</p>' * 20}</main></body></html>")
    assert SPEC.find_lines(body2) and not SPEC.find_affirmative(body2)  # 同じ行の否定は外す


def test_classify_facility_with_weak_event_word_in_name():  # 大垣市: 山村体験宿泊施設は施設
    assert sv.classify_page("大垣市かみいしづ緑の村公園・大垣市山村体験宿泊施設奥養老") == "facility"
    assert sv.classify_page("体験会のお知らせ") == "event"
    assert sv.classify_page("第56回四日市市民スポーツフェスタ開催について") == "event"


def test_fallback_seeds_find_sports_through_broad_categories():  # D-117: スポーツの入口が見つからない自治体
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/": page("トップ", '<a href="/bunka/">文化・生涯学習</a><a href="/news/">お知らせ</a><a href="/sitemap/">サイトマップ</a>'),
        "/bunka/": page("文化・生涯学習", '<a href="/bunka/sports/">スポーツ</a><a href="/bunka/lib/">図書館</a>'),
        "/bunka/sports/": page("スポーツ", '<a href="/f/1">中央運動場</a>'),
        "/f/1": page("中央運動場", "<p>グラウンド・ゴルフができます。</p>"),
        "/sitemap/": page("サイトマップ", '<a href="/bunka/sports/">スポーツ</a>'),
    }
    out = sv.survey_municipality(M, {"nav_links": [], "genre_entrypoints": []}, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t"))
    assert out["outcome"] == "surveyed" and out["seed_mode"] == "fallback" and out["found"]
    f1 = next(p for p in out["pages"] if p["url"].endswith("/f/1"))
    assert f1["hit"] and f1["depth"] == 2  # 大分類(深さ0)→スポーツ(1)→運動場(2)
    assert [s["role"] for s in out["seeds"]][0] == "broad" and out["seeds"][0]["text"] == "サイトマップ"


def test_fallback_seeds_ranking():
    links = [{"text": t, "url": f"https://x.jp/{i}", "same_site": True, "is_pdf": False} for i, t in enumerate(["お知らせ", "観光", "文化・生涯学習", "サイトマップ", "スポーツ", "予約システム"])]
    seeds = sv.fallback_seeds(links)
    assert [s["text"] for s in seeds] == ["サイトマップ", "スポーツ", "文化・生涯学習", "観光"]
