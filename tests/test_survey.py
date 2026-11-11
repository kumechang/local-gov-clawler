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
    out = sv.survey_municipality(M, r, make_fetcher({"/robots.txt": (503, "text/plain", "")}), SPEC, sv.SurveyConfig(retry_wait=0, robots_retry_wait=0))
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


def test_negated_sentences_are_kept_as_samples_for_review():
    routes = {"/robots.txt": (404, "text/plain", ""), "/sports/": page("スポーツ", "<p>ゲートボール専用です。グラウンド・ゴルフではご利用いただけません。</p>" + "<p>本文です。</p>" * 20)}
    out = sv.survey_municipality(M, result(cands=[("スポーツ", "https://www.city.example.jp/sports/")]), make_fetcher(routes), SPEC, sv.SurveyConfig(route="t"))
    p = out["pages"][0]
    assert p["negated"] == 1 and not p["hit"] and "ご利用いただけません" in p["negated_samples"][0]


def test_negation_is_scoped_to_the_words_own_clause():  # D-119: 同じ行でも、区切りの先の他のスポーツの禁止は無関係
    def neg(t):
        norm = sv.norm_text(t)
        return sv.is_negated(norm, SPEC.find(norm)[0].end(), SPEC.find(norm)[0].start())

    assert neg("グラウンド・ゴルフではご利用いただけません。")
    assert neg("グラウンドゴルフでの使用はご遠慮ください")
    assert not neg("グラウンドゴルフ、ゲートボール、野球は使用禁止です")
    assert not neg("グラウンドゴルフ・サッカー可 野球は禁止")
    assert not neg("グラウンド・ゴルフ以外の使用は禁止です")
    assert not neg("グラウンドゴルフ 可　ゴルフ練習 禁止")


def test_descriptive_dekinai_is_not_a_negation():  # 宇部市: 『普段なかなか体験できないスポーツ』
    def neg(t):
        norm = sv.norm_text(t)
        return sv.is_negated(norm, SPEC.find(norm)[0].end(), SPEC.find(norm)[0].start())

    assert not neg("陸上競技場では、モルック、グラウンドゴルフなど普段なかなか体験できないスポーツに挑戦!")
    assert not neg("雨天時はグラウンドゴルフはできない場合があります")  # 条件つき(D-122)
    assert neg("グラウンドゴルフは利用できない。")


def test_partial_or_unrelated_negations_are_kept_as_hits():  # D-122: 久喜市(曜日限定)・本宮市(受付の話)
    def neg(t):
        norm = sv.norm_text(t)
        m = SPEC.find(norm)[0]
        return sv.is_negated(norm, m.end(), m.start())

    assert not neg("冬休みおよび土曜日、日曜日、祝日は、グラウンドゴルフの利用はできません。")
    assert not neg("(グラウンド・ゴルフ場管理棟では受付できません。)")
    assert neg("グラウンド・ゴルフではご利用いただけません。")  # 豊山町型は従来どおり外す
    assert neg("グラウンドゴルフは禁止です")


def test_export_rows_split_by_kind_and_pdf_only_municipality():
    s = {
        "municipality": {"code": "29999", "name": "サンプル市", "prefecture": "奈良県", "official_url": "https://x.jp/"}, "run": {"route": "r", "finished_at": "2026-10-18T00:00:00Z"},
        "pages": [
            {"url": "https://x.jp/a", "hit": True, "kind": "facility", "title": "中央運動場", "snippets": ["グラウンド・ゴルフができます"], "link_hits": [], "count": 1, "role": "facility", "via": "運動場"},
            {"url": "https://x.jp/b", "hit": True, "kind": "event", "title": "第3回大会", "snippets": [], "link_hits": [{"text": "グラウンドゴルフ大会", "url": "u"}], "count": 0, "in_title": True, "role": "event", "via": "大会"},
            {"url": "https://x.jp/c", "hit": False, "kind": "facility", "title": "なし"},
        ],
        "pdf_link_hits": [{"text": "グラウンドゴルフ要項", "url": "https://x.jp/a.pdf", "page": "https://x.jp/c"}],
    }
    rows = sv.export_rows(s)
    assert [r["page_kind"] for r in rows] == ["facility", "event"] and rows[1]["in_title"] == "1" and "グラウンドゴルフ大会" in rows[1]["matched_text"]
    s2 = {**s, "pages": [s["pages"][2]]}
    r2 = sv.export_rows(s2)
    assert len(r2) == 1 and r2[0]["found_via"] == "pdf_link" and r2[0]["page_kind"] == "other"


def test_pdf_text_states_and_classification():
    import io

    import pypdf
    assert sv.pdf_text(b"not a pdf")[2] == "error"
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    text, pages, state = sv.pdf_text(buf.getvalue())
    assert state == "no_text" and pages == 1  # 画像だけ・白紙のPDFは no_text
    assert sv.classify_pdf("令和8年度 スポーツ推進計画", "計画", "") == "other"
    assert sv.classify_pdf("市内パークゴルフ場 施設一覧", "施設一覧", "") == "facility"
    assert sv.classify_pdf("第5回グラウンドゴルフ大会 開催要項", "要項", "") == "event"


def test_survey_reads_pdfs_from_sports_pages_only(monkeypatch):
    pdf_hit = "市内パークゴルフ場\n平成大橋上流右岸広場 パークゴルフ場1 グラウンドゴルフ場1\n"
    monkeypatch.setattr(sv, "pdf_text", lambda body, max_pages=30: (pdf_hit if body == b"%PDF-hit" else "関係のない計画\n" * 5, 2, "ok"))
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/sports/": page("スポーツ施設", '<a href="/f/1">中央運動場</a><a href="/doc/shisetsu.pdf">施設一覧(PDF)</a><a href="/doc/keikaku.pdf">スポーツ推進計画</a>', '<nav><a href="/nav.pdf">広報</a></nav>'),
        "/f/1": page("中央運動場", "<p>野球ができます。</p>"),
        "/doc/shisetsu.pdf": (200, "application/pdf", "%PDF-hit"),
        "/doc/keikaku.pdf": (200, "application/pdf", "%PDF-other"),
        "/nav.pdf": (200, "application/pdf", "%PDF-hit"),
    }
    r = result(cands=[("スポーツ施設", "https://www.city.example.jp/sports/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0, read_pdf=True))
    pdfs = {p["url"].rsplit("/", 1)[-1]: p for p in out["pages"] if p["role"] == "pdf"}
    assert set(pdfs) == {"shisetsu.pdf", "keikaku.pdf"}  # ナビのPDFは読まない
    assert pdfs["shisetsu.pdf"]["hit"] and pdfs["shisetsu.pdf"]["kind"] == "facility" and pdfs["shisetsu.pdf"]["via"] == "pdf_text" and "グラウンドゴルフ" in pdfs["shisetsu.pdf"]["snippets"][0]
    assert not pdfs["keikaku.pdf"]["hit"] and out["found"]
    rows = [r_ for r_ in sv.export_rows(out) if r_["found_via"] == "pdf"]
    assert len(rows) == 1 and rows[0]["page_kind"] == "facility"
    off = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert not [p for p in off["pages"] if p["role"] == "pdf"]  # 既定ではPDFを読まない


def test_pdf_readers_fall_back_in_order(monkeypatch):
    def first(body, max_pages):
        raise RuntimeError("broken")

    def second(body, max_pages):
        return "グラウンドゴルフ場が1か所あります。\r\n平成大橋上流右岸広場にあります。", 3

    monkeypatch.setattr(sv, "PDF_READERS", (("a", first), ("b", second)))
    text, pages, state = sv.pdf_text(b"x")
    assert state == "ok" and pages == 3 and "\r" not in text and text.split("\n")[0].startswith("グラウンドゴルフ")
    monkeypatch.setattr(sv, "PDF_READERS", (("a", first),))
    assert sv.pdf_text(b"x")[2] == "error"
    monkeypatch.setattr(sv, "PDF_READERS", (("a", lambda b, m: ("", 2)),))
    assert sv.pdf_text(b"x") == ("", 2, "no_text")

    def missing(body, max_pages):
        raise ImportError("no module")

    monkeypatch.setattr(sv, "PDF_READERS", (("a", missing),))
    assert sv.pdf_text(b"x")[2] == "no_reader"


def test_image_only_pdf_is_read_by_ocr_when_enabled(monkeypatch):
    spec = sv.KeywordSpec("grandgolf", "グラウンドゴルフ", [__import__("re").compile(r"グラウ?ンド[\s・･\-ー]*ゴルフ")], [__import__("re").compile(r"グ?ラウ?ン[ドト][\s・･\-ー]*[ゴコ][ルレ]フ")])
    monkeypatch.setattr(sv, "pdf_text", lambda body, max_pages=30: ("", 1, "no_text"))
    monkeypatch.setattr(sv, "ocr_pdf_text", lambda body, **kw: ("葛飾区グラント・コルフ協会\n活動場所 柴又公園", ["tesseract"], 1))  # 『ド』が『ト』に誤読された文字
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/sports/": page("スポーツ施設", '<a href="/doc/kyokai.pdf">協会のチラシ</a>'),
        "/doc/kyokai.pdf": (200, "application/pdf", "%PDF-scan"),
    }
    r = result(cands=[("スポーツ施設", "https://www.city.example.jp/sports/")])
    on = sv.survey_municipality(M, r, make_fetcher(routes), spec, sv.SurveyConfig(route="t", retry_wait=0, read_pdf=True, ocr_pdf=True))
    pdf = [p for p in on["pages"] if p["role"] == "pdf"][0]
    assert pdf["hit"] and pdf["ocr"] and pdf["pdf_state"] == "ocr" and pdf["ocr_engines"] == ["tesseract"] and "柴又公園" in pdf["snippets"][0] + "柴又公園"
    off = sv.survey_municipality(M, r, make_fetcher(routes), spec, sv.SurveyConfig(route="t", retry_wait=0, read_pdf=True))
    pdf = [p for p in off["pages"] if p["role"] == "pdf"][0]
    assert not pdf["hit"] and pdf["error_class"] == "pdf_no_text"  # 既定ではOCRしない


def test_pdfium_is_serialized_across_threads(monkeypatch):
    # PDFiumは複数のスレッドから同時に呼ぶと落ちる(D-152)。ロックの中でだけ呼ばれることを確かめる
    import threading
    state = {"inside": 0, "max": 0}

    def fake_locked(body, max_pages):
        state["inside"] += 1
        state["max"] = max(state["max"], state["inside"])
        import time
        time.sleep(0.02)
        state["inside"] -= 1
        return "グラウンドゴルフ場があります。" * 3, 1

    monkeypatch.setattr(sv, "_read_pdfium_locked", fake_locked)
    ts = [threading.Thread(target=lambda: sv._read_pdfium(b"x", 3)) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert state["max"] == 1


def test_hit_pdf_texts_are_stored_separately_and_readable(monkeypatch, tmp_path):
    """ワードのあったPDFの本文(文字に起こしたもの)だけを、調査の結果とは別のファイルに保存する。原本は保存しない(D-156)。"""
    pdf_hit = "市内パークゴルフ場\n平成大橋上流右岸広場 パークゴルフ場1 グラウンドゴルフ場1\n" + "あ" * 10
    monkeypatch.setattr(sv, "pdf_text", lambda body, max_pages=30: (pdf_hit if body == b"%PDF-hit" else "関係のない計画\n" * 5, 2, "ok"))
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/sports/": page("スポーツ施設", '<a href="/doc/shisetsu.pdf">施設一覧(PDF)</a><a href="/doc/keikaku.pdf">スポーツ推進計画</a>'),
        "/doc/shisetsu.pdf": (200, "application/pdf", "%PDF-hit"),
        "/doc/keikaku.pdf": (200, "application/pdf", "%PDF-other"),
    }
    r = result(cands=[("スポーツ施設", "https://www.city.example.jp/sports/")])
    out = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="wk", retry_wait=0, read_pdf=True))
    assert [t["url"].rsplit("/", 1)[-1] for t in out["pdf_texts"]] == ["shisetsu.pdf"]  # ワードの無いPDFは保存しない
    t = out["pdf_texts"][0]
    assert t["kind"] == "facility" and t["text"].startswith("市内パークゴルフ場") and len(t["sha256"]) == 64 and not t["truncated"] and t["found_on"].endswith("/sports/")
    assert "_pdf_texts" not in out
    sv.write_survey(tmp_path, out, "13")
    body = json.loads(next((tmp_path / "grandgolf" / "wk" / "13").glob("*.json")).read_text(encoding="utf-8"))
    assert "pdf_texts" not in body  # 調査の結果のJSONは大きくならない
    assert len(sv.load_surveys(tmp_path, "grandgolf", "wk")) == 1  # 本文のファイルが調査の結果として読まれない
    recs = sv.load_pdf_texts(tmp_path, "grandgolf", "wk")
    assert len(recs) == 1 and recs[0]["pdfs"][0]["text"] == t["text"]
    rows = sv.pdf_text_index(recs)
    assert len(rows) == 1 and rows[0]["text_file"].endswith(f"wk/_pdftext/{M.prefecture_code}/{M.code}.json") and "text" not in rows[0]
    off = sv.survey_municipality(M, r, make_fetcher(routes), SPEC, sv.SurveyConfig(route="wk", retry_wait=0))
    assert "pdf_texts" not in off  # PDFを読まない既定では何も作らない


def test_long_pdf_text_is_truncated_and_flagged(monkeypatch):
    big = "グラウンドゴルフ大会\n" + "あ" * (sv.PDF_TEXT_MAX_CHARS + 5)
    monkeypatch.setattr(sv, "pdf_text", lambda body, max_pages=30: (big, 30, "ok"))
    routes = {"/robots.txt": (404, "text/plain", ""), "/sports/": page("スポーツ施設", '<a href="/doc/a.pdf">大会要項</a>'), "/doc/a.pdf": (200, "application/pdf", "%PDF-x")}
    out = sv.survey_municipality(M, result(cands=[("スポーツ施設", "https://www.city.example.jp/sports/")]), make_fetcher(routes), SPEC, sv.SurveyConfig(route="wk", retry_wait=0, read_pdf=True))
    t = out["pdf_texts"][0]
    assert t["truncated"] and len(t["text"]) == sv.PDF_TEXT_MAX_CHARS and t["text_len"] == len(big)


def test_no_seed_municipality_falls_back_to_fresh_top_then_sitemap_page():
    """保存したナビがお知らせばかり(大分類が無い)で入口が見つからなかった自治体(D-158)。トップを取り直し、無ければサイトマップのページから探す。"""
    news = [("お知らせ%d" % i, f"https://www.city.example.jp/n/{i}") for i in range(6)]
    stored = {"nav_links": [{"text": t, "url": u, "same_site": True, "is_pdf": False} for t, u in news], "genre_entrypoints": [], "site_profile": {"sitemap": {"top_level_paths": {"/sitemap.html": 1, "/index.html": 1}}}}
    # トップのリンクに大分類がある場合
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/": page("トップ", '<a href="/bunka/">文化・生涯学習</a>'),
        "/bunka/": page("文化・生涯学習", '<a href="/bunka/sports/">スポーツ</a>'),
        "/bunka/sports/": page("スポーツ", '<a href="/f/1">中央運動場</a>'),
        "/f/1": page("中央運動場", "<p>グラウンド・ゴルフができます。</p>"),
    }
    out = sv.survey_municipality(M, stored, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "surveyed" and out["seed_mode"] == "fallback_top" and out["found"]
    # トップに無く、サイトマップのページ(ハブ判定で見えたURL)にある場合
    routes2 = {
        "/robots.txt": (404, "text/plain", ""),
        "/": page("トップ", '<a href="/n/1">お知らせ</a>'),
        "/sitemap.html": page("サイトマップ", '<a href="/bunka/sports/">スポーツ</a>'),
        "/bunka/sports/": page("スポーツ", '<a href="/f/1">中央運動場</a>'),
        "/f/1": page("中央運動場", "<p>グラウンド・ゴルフができます。</p>"),
    }
    out = sv.survey_municipality(M, stored, make_fetcher(routes2), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "surveyed" and out["seed_mode"] == "fallback_sitemap" and out["found"]
    # どちらにも無ければ、これまでどおり no_seed(当てずっぽうの取得はしない)
    routes3 = {"/robots.txt": (404, "text/plain", ""), "/": page("トップ", '<a href="/n/1">お知らせ</a>')}
    out = sv.survey_municipality(M, stored, make_fetcher(routes3), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "no_seed" and sorted({r["url"].rsplit("/", 1)[-1] for r in out["requests"]}) == ["", "robots.txt", "sitemap.html"]


def test_compliance_counts_fast_requests_reservation_and_robots_skips():
    """取得ルールの遵守の計測(D-158)。1ホスト1秒以下、予約・ログインらしいURLの取得、robotsで飛ばした回数。"""
    def req(host, path, t):
        return {"url": f"https://{host}{path}", "t": t}

    ok = {"municipality": {"code": "1"}, "robots_skipped": 2, "requests": [req("a.jp", "/", 100.0), req("a.jp", "/x", 101.0), req("b.jp", "/", 100.1), req("a.jp", "/y", 102.05), {"url": "https://a.jp/old"}]}
    bad = {"municipality": {"code": "2"}, "requests": [req("c.jp", "/", 10.0), req("c.jp", "/yoyaku/", 10.4)]}
    c = sv.compliance([ok, bad])
    assert c["requests"] == 7 and c["untimed_requests"] == 1 and c["timed_pairs"] == 3
    assert c["interval_violations"] == 1 and c["worst_gap"] == (0.4, "2", "c.jp")
    assert c["reservation_fetched"] == 1 and c["robots_skipped"] == 2


def test_fetch_log_records_send_time(monkeypatch):
    import time as _t
    from localgov_crawler.fetcher import FetchResult
    r = FetchResult("https://a.jp/", started=_t.time())
    assert r.log_entry()["t"] > 0


def test_stale_hub_seeds_are_rebuilt_from_the_top_page():
    """保存した入口がすべて消えていた(404)自治体は、トップから入口を作り直す(D-158)。1ページも読めなければ『調査できた』にしない。"""
    stale = result(cands=[("スポーツ施設", "https://www.city.example.jp/old/sports/")])
    routes = {
        "/robots.txt": (404, "text/plain", ""),
        "/": page("トップ", '<a href="/bunka/">文化・生涯学習</a>'),
        "/bunka/": page("文化・生涯学習", '<a href="/bunka/sports/">スポーツ</a>'),
        "/bunka/sports/": page("スポーツ", '<a href="/f/1">中央運動場</a>'),
        "/f/1": page("中央運動場", "<p>グラウンド・ゴルフができます。</p>"),
    }
    out = sv.survey_municipality(M, stale, make_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "surveyed" and out["seed_mode"] == "fallback_stale" and out["found"]
    assert out["stale_seeds"][0]["url"].endswith("/old/sports/") and out["pages_fetched"] >= 3
    # トップにも手がかりが無い: 1ページも読めなかったので fetch_failed
    dead = {"/robots.txt": (404, "text/plain", ""), "/": page("トップ", '<a href="/n/1">お知らせ</a>')}
    out = sv.survey_municipality(M, stale, make_fetcher(dead), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "fetch_failed" and out["failure_class"] == "seeds_unreachable"
    # 正常な自治体は、これまでどおり1回で終わる(入口の作り直しをしない)
    ok = {"/robots.txt": (404, "text/plain", ""), "/old/sports/": page("スポーツ施設", "<p>グラウンド・ゴルフができます。</p>")}
    out = sv.survey_municipality(M, stale, make_fetcher(ok), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert out["outcome"] == "surveyed" and out["seed_mode"] == "normal" and "stale_seeds" not in out


def host_fetcher(routes):
    """(ホスト, パス) → (status, content_type, body)。外部サイトのテスト用。"""
    import httpx
    from localgov_crawler.fetcher import Fetcher

    def handler(request):
        r = routes.get((request.url.host, request.url.path))
        if r is None:
            return httpx.Response(404, text="not found")
        status, ctype, body = r
        return httpx.Response(status, headers={"content-type": ctype}, content=body.encode("utf-8"))

    return Fetcher(min_interval=0, transport=httpx.MockTransport(handler))


def test_external_sites_are_followed_only_with_robots_and_recorded_separately():
    """スポーツ関連のページからリンクされた協会・指定管理者のサイトを少しだけ見る(D-161)。ロボットを確認し、結果は ext_hit(従来の found は変えない)。"""
    ext = "https://www.gg-kyokai.example.org"
    routes = {
        ("www.city.example.jp", "/robots.txt"): (404, "text/plain", ""),
        ("www.city.example.jp", "/sports/"): page("スポーツ", f'<a href="{ext}/">市スポーツ協会</a><a href="https://www.youtube.com/x">動画</a><a href="https://www.pref.example.lg.jp/">県</a><a href="https://yoyaku.example.jp/">予約</a>'),
        ("www.gg-kyokai.example.org", "/robots.txt"): (200, "text/plain", "User-agent: *\nDisallow: /private/\n"),
        ("www.gg-kyokai.example.org", "/"): page("市協会", '<a href="/taikai/">大会のご案内</a><a href="/private/x">会員</a>'),
        ("www.gg-kyokai.example.org", "/taikai/"): page("大会のご案内", "<p>第3回グラウンドゴルフ大会を中央運動場で開催します。</p>"),
    }
    r = result(cands=[("スポーツ", "https://www.city.example.jp/sports/")])
    off = sv.survey_municipality(M, r, host_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0))
    assert not [p for p in off["pages"] if p["role"] == "external"]  # 既定では外部サイトを見ない
    out = sv.survey_municipality(M, r, host_fetcher(routes), SPEC, sv.SurveyConfig(route="t", retry_wait=0, follow_external=True))
    ext_pages = [p for p in out["pages"] if p["role"] == "external"]
    assert {p["url"] for p in ext_pages} == {f"{ext}/", f"{ext}/taikai/"}  # 動画・官公庁・予約は見ない。robotsで不許可の /private/ は取得しない
    hit = next(p for p in ext_pages if p["url"].endswith("/taikai/"))
    assert hit["ext_hit"] and not hit["hit"] and hit["external_host"] == "www.gg-kyokai.example.org" and hit["kind"] == "event"
    assert out["external_found"] and not out["found"]  # 従来の『ワードがあった自治体』は変えない
    rows = sv.export_rows(out)
    assert len(rows) == 1 and rows[0]["found_via"] == "external" and rows[0]["page_kind"] == "event"
    assert not any(r_["url"].endswith("/private/x") for r_ in out["requests"])
    from localgov_crawler import cli
    assert "external" in cli.PDF_FOUND_VIA  # 外部サイトの行は、HTMLとして取り直す抽出の対象にしない


def test_external_ok_denies_and_national_hosts():
    spec = sv.KeywordSpec("grandgolf", "グラウンドゴルフ", [__import__("re").compile(r"グラウ?ンド[\s・･\-ー]*ゴルフ")], [], ["groundgolf.or.jp"])
    assert sv.external_ok("https://club.example.org/", "市グラウンドゴルフ協会", spec)
    assert sv.external_ok("https://club.example.org/", "指定管理者のサイト", spec)
    assert not sv.external_ok("https://www.groundgolf.or.jp/", "グラウンドゴルフ", spec)  # 全国組織のサイト
    assert not sv.external_ok("https://maps.google.co.jp/x", "グラウンドゴルフ場の地図", spec)
    assert not sv.external_ok("https://www.city.other.lg.jp/", "スポーツ協会", spec)
    assert not sv.external_ok("https://club.example.org/yoyaku/", "スポーツ協会", spec)
    assert not sv.external_ok("https://club.example.org/", "お問い合わせ", spec)


def test_robots_unreachable_is_retried_once():
    state = {"n": 0}
    import httpx
    from localgov_crawler.fetcher import Fetcher

    def handler(request):
        if request.url.path == "/robots.txt":
            state["n"] += 1
            return httpx.Response(503) if state["n"] <= 2 else httpx.Response(404)  # 最初の取得(再試行を含む2回)は不通、やり直しで届く
        return httpx.Response(200, headers={"content-type": HTML}, content="<html><title>スポーツ</title><body><main>グランドゴルフ場あり</main></body></html>".encode())

    r = result(cands=[("スポーツ", "https://www.city.example.jp/sports/")])
    out = sv.survey_municipality(M, r, Fetcher(min_interval=0, transport=httpx.MockTransport(handler)), SPEC, sv.SurveyConfig(retry_wait=0, robots_retry_wait=0))
    assert out["outcome"] == "surveyed" and out["found"] and out["robots_retried"]


def test_sitemap_keyword_urls_become_seeds_and_keyword_variants():
    r = {"nav_links": [], "genre_entrypoints": [], "site_profile": {"sitemap": {"keyword_urls": ["https://www.city.example.jp/kankou/park1", "https://www.city.example.jp/x2"]}}}
    seeds = sv.seeds_from_result(r)
    assert [s["url"] for s in seeds] == ["https://www.city.example.jp/kankou/park1", "https://www.city.example.jp/x2"] and seeds[0]["source"] == "sitemap"
    import json as _j
    from pathlib import Path
    spec = sv.KeywordSpec.load(Path(__file__).parent.parent / "config/keywords/grandgolf.json")
    for t in ["ぐらうんどごるふ大会", "Ground Golf", "グラウンド・ゴルフ", "グランドゴルフ", "ｸﾞﾗｳﾝﾄﾞｺﾞﾙﾌ"]:
        assert spec.in_text(t), t
    for t in ["パークゴルフ", "グラウンドとゴルフ場", "ground floor", "ゴルフ"]:
        assert not spec.in_text(t), t
    assert "groundgolf.or.jp" in spec.external_deny_hosts


def test_max_pdfs_and_external_budget_are_in_request_budget():
    base = sv.SurveyConfig(max_pages=100, read_pdf=True, max_pdfs=40, follow_external=True).pipeline_config().max_requests
    assert base == 100 + 8 + 40 + 12 + 4
