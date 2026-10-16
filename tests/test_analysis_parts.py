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


def cand(url, score, kind, depth=1, fl=None, fetched=True, text="x"):
    return hub.Candidate(url, text, score, reasons=["text:x"], depth=depth, fetched=fetched, facility_link_count=fl, kind=kind)


def test_classify_label():
    k = hub.classify_label
    assert k("スポーツ・体育") == k("スポーツ施設一覧") == k("体育施設") == k("スポーツ情報") == "sports_pure"
    assert k("観光・文化・スポーツ") == k("生涯学習・スポーツ") == k("健康・スポーツ") == k("文化・スポーツ施設") == "sports_composite"
    assert k("学校体育施設の利用") == "sports_composite"
    assert k("三宅町体育館") == k("屋敷山公園内 体育施設情報") == "sports_other"
    assert k("公共施設一覧") == k("施設を探す") == k("町の施設") == "generic"
    assert k("教育") == k("くらし・手続き") == k("サイトマップ") == "broad"
    assert k("子育て") == "other"


def test_decide_precision_first():
    # 専用ラベルで施設名リンクのある候補は確定
    assert hub.decide([cand("a", 12, "sports_pure", fl=4)]).outcome == "hub_selected"
    # 施設名リンクが1件だけのページは一覧とみなさない(橿原市の「スポーツ」小分類型)
    assert hub.decide([cand("a", 12, "sports_pure", fl=1)]).outcome == "hub_not_found"
    assert hub.decide([cand("a", 12, "sports_pure", fl=2)]).outcome == "hub_selected"
    # 同じ深さで僅差なら確定しない(後段のAI/手動へ)
    assert hub.decide([cand("a", 12, "sports_pure", fl=4), cand("b", 11, "sports_pure", fl=3)]).outcome == "hub_multiple"
    # 浅い方が高得点でなくても、浅い専用ラベルを優先(トップに近い一覧が正解の定義)
    d = hub.decide([cand("shallow", 12, "sports_pure", 1, 4), cand("deep", 25, "sports_pure", 2, 23)])
    assert d.outcome == "hub_selected" and d.selected.url == "shallow"
    # ページ未確認の候補は確定しない。有望ならhub_multiple(次の段階へ)
    assert hub.decide([cand("x", 12, "sports_pure", 3, None, fetched=False)]).outcome == "hub_multiple"
    assert hub.decide([cand("x", 5, "sports_pure", 3, None, fetched=False)]).outcome == "hub_not_found"


def test_decide_composite_and_empty_categories_are_not_hubs():
    # 生駒市型: ラベルに「スポーツ施設」を含む複合ラベルでも、施設名リンクが無ければ採用しない。専用ページ(深さ2)を採用
    d = hub.decide([cand("composite", 16, "sports_composite", 1, 0, text="文化・スポーツ施設"), cand("pure", 19, "sports_pure", 2, 6)])
    assert d.selected.url == "pure"
    # 葛城市型: 施設名リンクがあっても、強い語を含まない複合ラベル(観光・文化・スポーツ)は採用しない
    d = hub.decide([cand("kbs", 12, "sports_composite", 1, 4, text="観光・文化・スポーツ"), cand("sports", 9, "sports_pure", 2, 3)])
    assert d.selected.url == "sports"
    # 強い語を含む複合ラベルは、施設名リンクが3件以上あれば採用可能
    assert hub.decide([cand("c", 13, "sports_composite", 1, 5, text="公民館・文化・スポーツ施設")]).outcome == "hub_selected"
    assert hub.decide([cand("c", 13, "sports_composite", 1, 2, text="公民館・文化・スポーツ施設")]).outcome == "hub_not_found"
    # 大分類は何点でも採用しない
    assert hub.decide([cand("b", 30, "broad", 1, 9)]).outcome == "hub_not_found"
    # 個別施設ページ(施設名リンク1件以下)は採用しない
    assert hub.decide([cand("f", 14, "sports_other", 2, 0, text="屋敷山公園内 体育施設情報")]).outcome == "hub_not_found"


def test_decide_generic_facility_list_only_when_no_specific():
    d = hub.decide([cand("g", 11, "generic", 1, 8, text="施設一覧")])
    assert d.outcome == "hub_selected" and d.quality == "generic"
    d = hub.decide([cand("g", 11, "generic", 1, 8), cand("s", 10, "sports_pure", 2, 3)])
    assert d.selected.url == "s" and d.quality == "specific"
    assert hub.decide([cand("g", 11, "generic", 1, 2)]).outcome == "hub_not_found"  # 施設名リンクが少ない


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


def test_decide_strong_label_beats_shallower_weak_label():
    """生駒市型: 浅い「スポーツ」(弱いラベル)より、深い「スポーツ施設」(強いラベル)を優先する。"""
    weak = cand("weak", 11, "sports_pure", 1, 2, text="スポーツ")
    strong = cand("strong", 23, "sports_pure", 2, 6, text="スポーツ施設")
    assert hub.decide([weak, strong]).selected.url == "strong"
    # 奈良市型: 強いラベル同士なら浅い方(トップに近い一覧)を選ぶ
    d = hub.decide([cand("shallow", 25, "sports_pure", 1, 7, text="スポーツ施設"), cand("deep", 29, "sports_pure", 2, 23, text="スポーツ施設一覧")])
    assert d.selected.url == "shallow"
    # 強いラベルが無ければ、これまでどおり弱いラベルを使う(葛城市型)
    assert hub.decide([weak]).selected.url == "weak"


def test_ground_word_is_only_a_sports_ground():
    """福井県パイロットの坂井市: 「三国グランドビジョン」(防災整備計画)を運動場と誤認していた。"""
    assert hub.classify_label("三国グランドビジョン") == "other"
    assert hub.score_text("三国グランドビジョン")[0] == 0
    assert not hub.FACILITY_NAME.search("グランドホテル")
    # 運動場としての「グラウンド/グランド」は引き続き有効
    for t in ["中央グラウンド", "市民グランド", "グランドゴルフ場", "グランド使用の案内", "グランド・野球場", "グランド"]:
        assert hub.classify_label(t).startswith("sports"), t
        assert hub.FACILITY_NAME.search(t), t


def test_page_features_reports_counted_links_for_diagnosis():
    html = '<html><body><nav><a href="/a">市民体育館</a></nav><main><a href="/b">中央グラウンド</a><a href="/c">お知らせ</a></main></body></html>'
    soup = parse_html(html)
    n, head, samples = hub.page_features(soup, extract_links(soup, "https://x.jp/", "x.jp"))
    assert n == 2 and samples == ["市民体育館[nav]", "中央グラウンド[main]"]


def test_duplicate_facility_links_are_counted_once():
    """川上村型: 同じ公園へのリンクが、空白の違いで2件に数えられていた。"""
    html = ('<html><body><main><a href="/p">あきつの小野スポーツ公園</a></main>'
            '<nav><a href="/p2">あきつの小野 スポーツ公園</a><a href="/p">スポーツ公園の案内(別文言)</a></nav></body></html>')
    soup = parse_html(html)
    n, _, samples = hub.page_features(soup, extract_links(soup, "https://x.jp/", "x.jp"))
    assert n == 1 and len(samples) == 1
    html2 = '<html><body><a href="/a">市民体育館</a><a href="/b">中央グラウンド</a></body></html>'
    soup2 = parse_html(html2)
    assert hub.page_features(soup2, extract_links(soup2, "https://x.jp/", "x.jp"))[0] == 2


def test_procedure_pages_are_not_hubs_but_categories_still_explored():
    """あわら市型: 「スポーツ施設の利用申請について」は一覧ではない。「くらし・手続き」の大分類は探索対象のまま。"""
    assert hub.score_text("スポーツ施設の利用申請について", "", "other")[0] < hub.FETCH_MIN + 2
    assert hub.score_text("スポーツ施設", "", "nav")[0] >= hub.MIN_SCORE
    assert hub.score_text("くらし・手続き", "", "nav")[0] >= hub.FETCH_MIN
    assert hub.score_text("体育施設利用案内", "", "nav")[0] >= hub.MIN_SCORE


def test_news_titles_are_not_counted_as_facility_links():
    """安堵町型: 「体育館の雨漏修繕工事」「広場開放のお知らせ」などの題名を施設名リンクに数えていた。"""
    html = ('<html><body><nav>'
            '<a href="/n1">安堵中央公園体育館 雨漏修繕工事および空調設備工事のため休館します</a>'
            '<a href="/n2">安堵中央公園多目的広場開放のお知らせ</a>'
            '<a href="/n3">【条件付き一般競争入札の結果】体育館空調</a>'
            '</nav><main><a href="/f1">安堵中央公園体育館</a><a href="/f2">安堵中央公園多目的広場</a></main></body></html>')
    soup = parse_html(html)
    n, _, samples = hub.page_features(soup, extract_links(soup, "https://x.jp/", "x.jp"))
    assert n == 2 and all("お知らせ" not in x and "工事" not in x for x in samples)
    # 施設の案内ページへのリンク(「〜のご案内」)は施設名リンクとして数える
    html2 = '<html><body><a href="/a">下市中央公園総合体育館のご案内</a><a href="/b">奈良県下市健民運動場のご案内</a></body></html>'
    soup2 = parse_html(html2)
    assert hub.page_features(soup2, extract_links(soup2, "https://x.jp/", "x.jp"))[0] == 2


def _viable(text, fl=5):
    sc, reasons = hub.score_text(text, "", "nav")
    c = hub.Candidate("https://x.jp/a", text, sc, reasons, kind=hub.classify_label(text))
    hub.rescore_with_page(c, fl, text)
    return hub.is_viable(c)


def test_project_opening_and_system_pages_are_not_auto_selected():
    """段階1(愛知・大阪)で確定してしまった、施設の一覧ではないページ(D-067)。"""
    for label in ["龍北総合運動場整備事業", "スポーツ施設の整備", "学校体育施設開放事業", "学校体育施設開放案内",
                  "OPAS(オーパススポーツ施設情報システム)"]:
        assert not _viable(label), label
    # 通常の一覧ページは、これまでどおり確定できる
    for label in ["スポーツ施設", "スポーツ施設一覧", "体育施設", "運動施設", "社会体育施設"]:
        assert _viable(label), label


def test_notices_and_course_titles_are_not_facility_links_v8():
    html = ('<html><body><main>'
            '<a href="/1">市民総合体育館空調設備設置(スポーツ振興くじ助成)</a>'
            '<a href="/2">市民総合体育館トレーニング講習会</a>'
            '<a href="/3">下里総合運動場を硬式野球等でご利用される皆さんへ</a>'
            '<a href="/4">市民プール(屋外冷水プール)開場のご案内</a>'
            '<a href="/5">市民総合体育館</a><a href="/6">下里総合運動場</a>'
            '</main></body></html>')
    soup = parse_html(html)
    n, _, samples = hub.page_features(soup, extract_links(soup, "https://x.jp/", "x.jp"))
    assert n == 2 and samples == ["市民総合体育館[main]", "下里総合運動場[main]"]


def test_body_facility_terms_count_only_text_outside_links():
    """診断(判定には使わない、D-068): 施設名がリンクでなく本文・表の文字で並ぶページの見分け用。"""
    html = ('<html><head><title>スポーツ施設 体育館</title></head><body><nav><a href="/a">市民体育館</a></nav>'
            '<main><table><tr><td>総合体育館</td><td>テニスコート</td></tr><tr><td>第二体育館</td><td>市民プール</td></tr></table>'
            '<p>野球場の予約は<a href="/r">体育館の予約</a>から</p></main><script>var 体育館=1;</script></body></html>')
    got = hub.body_facility_terms(parse_html(html))
    assert got == {"体育館": 2, "テニスコート": 1, "プール": 1, "野球場": 1}
