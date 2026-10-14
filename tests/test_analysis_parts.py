from localgov_crawler import hub
from localgov_crawler.cms import detect_cms
from localgov_crawler.html import decode_bytes, parse_html
from localgov_crawler.nav import extract_links, find_menu_labels
from localgov_crawler.rendering import assess_rendering

from conftest import fixture_text


def test_decode_shift_jis_and_euc():
    sjis = '<html><head><meta charset="Shift_JIS"></head><body>体育館</body></html>'.encode("cp932")
    assert "体育館" in decode_bytes(sjis)
    assert "体育館" in decode_bytes("体育館".encode("euc_jp"), "text/html; charset=EUC-JP")


def test_extract_links_filters_and_regions():
    html = fixture_text("top_city.html")
    links = extract_links(parse_html(html), "https://www.city.example.jp/", "city.example.jp")
    by_text = {l.text: l for l in links}
    assert by_text["スポーツ施設"].url == "https://www.city.example.jp/sports/shisetsu.html"
    assert by_text["くらし・手続き"].region == "nav"
    assert not by_text["外部サイト"].same_site
    assert "メール" not in by_text
    assert "分野別" in find_menu_labels(parse_html(html))


def test_cms_detection():
    html = fixture_text("top_city.html")
    g = detect_cms(html, parse_html(html), [])
    assert g.family == "wordpress" and g.confidence == "high"
    g2 = detect_cms("<html></html>", parse_html("<html></html>"), ["https://x.jp/soshiki/1/2.html", "https://x.jp/soshiki/3/4.html"])
    assert g2.family == "url_pattern:soshiki_numeric"
    assert detect_cms("<html></html>", parse_html("<html></html>"), []).family == "unknown"


def test_rendering():
    spa = '<html><body><div id="app"></div><noscript>JavaScriptを有効にしてください</noscript><script src="a.js"></script></body></html>'
    assert assess_rendering(spa, parse_html(spa)).needs_headless
    big = "<html><body>" + "".join(f'<a href="/p{i}">リンク{i}</a>' for i in range(30)) + "本文" * 200 + "</body></html>"
    assert not assess_rendering(big, parse_html(big)).needs_headless


def test_score_text():
    assert hub.score_text("スポーツ施設")[0] >= hub.MIN_SCORE
    assert hub.score_text("体育施設一覧", "https://a.jp/taiiku/", "nav")[0] > hub.score_text("体育施設一覧")[0]
    assert hub.score_text("スポーツ大会の参加者を募集します")[0] < hub.MIN_SCORE
    assert hub.score_text("体育館予約システム")[0] < hub.MIN_SCORE
    assert hub.score_text("子育て")[0] == 0
    assert hub.score_text("スポーツ施設")[0] == hub.score_text("ｽﾎﾟｰﾂ施設")[0]  # NFKC


def test_decide():
    c = lambda u, s: hub.Candidate(u, u, s, reasons=["text:x"])
    assert hub.decide([c("a", 12), c("b", 5)]).outcome == "hub_selected"
    assert hub.decide([c("a", 12), c("b", 11)]).outcome == "hub_multiple"
    assert hub.decide([c("a", 5)]).outcome == "hub_not_found"
    assert hub.decide([c("a", 12), c("a", 3)]).outcome == "hub_selected"
    assert hub.decide([]).outcome == "hub_not_found"


def test_new_scoring_cases_from_pilot():
    s = lambda t, region="nav": hub.score_text(t, "", region)[0]
    # 大分類・探索用の入口は「先を見に行く」点数にはなるが、確定点数には届かない
    for t in ["施設を探す", "町の施設", "教育・文化・スポーツ", "教育", "生涯学習"]:
        assert hub.FETCH_MIN <= s(t) < hub.MIN_SCORE, t
    # 子育て・文化財・教育委員会は探索対象にしない
    for t in ["子育て・教育", "文化財", "教育委員会", "観光・文化財"]:
        assert s(t) < hub.FETCH_MIN, t
    # 実際にハブになっていたお知らせ記事
    for t in ["社会体育施設の熱中症対策について", "学校体育施設利用手続きの改正について", "御所スポーツフェスティバル2026", "天理市体育施設指定管理者募集"]:
        assert s(t, "other") < hub.MIN_SCORE, t
        assert s(t, "other") < hub.FETCH_MIN + 2, t
    assert s("スポーツ施設") >= hub.MIN_SCORE and s("体育施設案内") >= hub.MIN_SCORE


def test_decide_prefers_shallow_viable_over_deep_facility():
    c = lambda u, s, d, fetched=False, fl=None: hub.Candidate(u, "", s, reasons=["text:x"], depth=d, fetched=fetched, facility_link_count=fl)
    d = hub.decide([c("list", 12, 1, True, 4), c("facility", 13, 2)])
    assert d.outcome == "hub_selected" and d.selected.url == "list"
    # 浅い階層に採用可能な候補がなければ深い階層を使う
    assert hub.decide([c("cat", 9, 1, True, 0), c("facility", 13, 2)]).selected.url == "facility"
    # 同じ深さで僅差なら複数扱い
    assert hub.decide([c("a", 12, 1), c("b", 11, 1)]).outcome == "hub_multiple"
    # 施設リンクの無い大分類は、強い語の見出しでない限り採用しない
    assert hub.decide([c("cat", 9, 1, True, 0)]).outcome == "hub_not_found"


def test_cms_url_patterns_from_pilot():
    def fam(urls):
        return detect_cms("<html></html>", parse_html("<html></html>"), urls).family
    base = "https://x.jp"
    assert fam([f"{base}/category/3-4-0-0-0-0-0-0-0-0.html", f"{base}/0000003746.html"]) == "url_pattern:category_numeric"
    assert fam([f"{base}/life/1/7/36/", f"{base}/life/3/23/"]) == "url_pattern:life_numeric"
    assert fam([f"{base}/contents_detail.php?frmId=160", f"{base}/category_list.php?x=1"]) == "url_pattern:php_query"
    assert fam([f"{base}/kanko_bunka_sports/sports/5796.html"]) == "url_pattern:genre_dir_index"


def test_nav_image_only_links_and_rendering():
    html = '<html><body><a href="/life"><img src="images/kurashi.png"></a><img src="a.jpg"><img src="b.jpg"></body></html>'
    soup = parse_html(html)
    links = extract_links(soup, "https://x.jp/", "x.jp")
    assert [(l.text, l.text_kind) for l in links] == [("kurashi", "img_src")]
    assert not assess_rendering(html, soup).needs_headless
    # 画像もリンクも無い空の殻は引き続きJS描画扱い
    shell = '<html><body><div id="root"></div></body></html>'
    assert assess_rendering(shell, parse_html(shell)).needs_headless
