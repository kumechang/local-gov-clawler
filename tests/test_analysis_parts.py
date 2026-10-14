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
    c = lambda u, s: hub.Candidate(u, u, s)
    assert hub.decide([c("a", 12), c("b", 5)]).outcome == "hub_selected"
    assert hub.decide([c("a", 12), c("b", 11)]).outcome == "hub_multiple"
    assert hub.decide([c("a", 5)]).outcome == "hub_not_found"
    assert hub.decide([c("a", 12), c("a", 3)]).outcome == "hub_selected"
    assert hub.decide([]).outcome == "hub_not_found"
