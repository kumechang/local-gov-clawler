from conftest import make_fetcher
from localgov_crawler import extract as ex
from localgov_crawler import survey as sv
from localgov_crawler.municipalities import Municipality

import re

SPEC = sv.KeywordSpec("grandgolf", "グラウンドゴルフ", [re.compile(r"グラウ?ンド[\s・･\-ー]*ゴルフ")])
HTML = "text/html; charset=utf-8"
M = Municipality("29999", "サンプル市", "サンプル市", "29", "奈良県", "city", "municipality", "", "https://www.city.example.jp/", "", "")


def test_find_phones_formats_and_postal_codes():
    assert ex.find_phones("電話 0533-89-2111(代表)") == ["0533-89-2111"]
    assert ex.find_phones("TEL:(0568)51-1234 FAX 0568-51-5678") == ["0568-51-1234", "0568-51-5678"]
    assert ex.find_phones("〒480-0292 愛知県 電話０９０－１２３４－５６７８") == ["090-1234-5678"]
    assert ex.find_phones("〒060-0001 札幌市") == []  # 郵便番号は電話でない
    assert ex.find_phones("令和8年4月1日 2026-10-18") == []


def test_clean_name_removes_site_name():
    assert ex.clean_name("桜ヶ丘公園(グラウンド)/豊川市", "豊川市") == "桜ヶ丘公園(グラウンド)"
    assert ex.clean_name("安城市/安城市西部グラウンドゴルフ場", "安城市") == "安城市西部グラウンドゴルフ場"
    assert ex.clean_name("施設案内 大八グラウンド|高山市公式ホームページ", "高山市") == "大八グラウンド"


def test_single_facility_page_with_key_value_table_and_inquiry():
    html = """<html><head><title>桜ヶ丘公園(グラウンド)/サンプル市</title></head><body><h1>桜ヶ丘公園(グラウンド)</h1>
    <table><tr><th>所在地</th><td>サンプル市桜ヶ丘町79-2 地図を見る</td></tr><tr><th>電話番号</th><td>0533-89-2111</td></tr>
    <tr><th>利用可能種目</th><td>サッカー、グラウンド・ゴルフ</td></tr></table>
    <div class="inq">お問い合わせ先 スポーツ課 電話 0533-89-0000</div></body></html>"""
    r = ex.extract_page(html, "サンプル市", SPEC)
    assert r["page_name"] == "桜ヶ丘公園(グラウンド)" and not r["multi_facility"]
    it = r["items"][0]
    assert it["address"] == "サンプル市桜ヶ丘町79-2" and it["phone"] == "0533-89-2111"
    assert r["inquiry"]["phone"] == "0533-89-0000" and "スポーツ課" in r["inquiry"]["dept"]


def test_list_table_gives_one_item_per_facility_and_marks_keyword_rows():
    html = """<html><head><title>体育施設|サンプル市</title></head><body><h1>体育施設</h1><table>
    <tr><th>施設名</th><th>所在地</th><th>電話</th><th>利用種目</th></tr>
    <tr><td>中央運動場</td><td>サンプル市中央1-1</td><td>0742-11-1111</td><td>野球、グラウンドゴルフ</td></tr>
    <tr><td>市民体育館</td><td>サンプル市中央2-2</td><td>0742-22-2222</td><td>バスケットボール</td></tr></table></body></html>"""
    r = ex.extract_page(html, "サンプル市", SPEC)
    assert r["multi_facility"] and [i["name"] for i in r["items"]] == ["中央運動場", "市民体育館"]
    assert [i["keyword_in_item"] for i in r["items"]] == [True, False]
    rec = {"municipality": {"prefecture": "奈良県", "code": "29999", "name": "サンプル市", "official_url": "x"}, "run": {"route": "t", "finished_at": "z"}, "pages": [{**r, "page_url": "https://x/a", "matched_text": ""}]}
    rows = ex.detail_rows(rec)
    assert [x["facility_name"] for x in rows] == ["中央運動場"]  # 一覧は、ワードのある施設の行だけ


def test_sections_by_heading_and_text_fallback():
    html = """<html><head><title>公園|サンプル市</title></head><body><h1>公園</h1>
    <h2>東公園グラウンド</h2><dl><dt>所在地</dt><dd>サンプル市東町3-4</dd><dt>電話</dt><dd>0742-33-3333</dd></dl><p>グラウンドゴルフができます</p>
    <h2>西公園</h2><dl><dt>住所</dt><dd>サンプル市西町5-6</dd></dl></body></html>"""
    r = ex.extract_page(html, "サンプル市", SPEC)
    assert [(i["name"], i["address"], i["phone"]) for i in r["items"]] == [("東公園グラウンド", "サンプル市東町3-4", "0742-33-3333"), ("西公園", "サンプル市西町5-6", "")]
    txt = ex.extract_page("<html><head><title>広場|サンプル市</title></head><body><h1>広場</h1><p>所在地:サンプル市南町7-8 利用時間 9時</p><p>お問い合わせは0742-44-4444まで</p></body></html>", "サンプル市", SPEC)
    assert txt["items"][0]["address"] == "サンプル市南町7-8" and txt["items"][0]["phone"] == "0742-44-4444" and txt["items"][0]["source"].startswith("kv")


def test_extract_municipality_fetches_pages_and_respects_robots():
    routes = {
        "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /secret/\n"),
        "/f/1": (200, HTML, "<html><head><title>運動場|サンプル市</title></head><body><h1>運動場</h1><table><tr><th>所在地</th><td>サンプル市1-1</td></tr><tr><th>電話</th><td>0742-11-1111</td></tr></table></body></html>"),
    }
    pages = [{"page_url": "https://www.city.example.jp/f/1", "page_title": "運動場", "matched_text": "グラウンド・ゴルフ"}, {"page_url": "https://www.city.example.jp/secret/x", "page_title": "x", "matched_text": ""}, {"page_url": "https://www.city.example.jp/f/404"}]
    rec = ex.extract_municipality(M, pages, make_fetcher(routes), SPEC, ex.ExtractConfig(route="t"))
    assert rec["outcome"] == "extracted" and rec["pages"][0]["items"][0]["phone"] == "0742-11-1111"
    assert rec["pages"][1]["error_class"] == "robots_disallowed" and "items" not in rec["pages"][1] and rec["pages"][2]["status"] == 404


def test_address_is_cut_to_the_first_chunk():  # v2: 『設備 ソフトボール場…』まで取り込まない
    assert ex.clean_address("豊川市桜ヶ丘町79-2 設備 ソフトボール場 1面 利用料金 無料") == "豊川市桜ヶ丘町79-2"
    assert ex.clean_address("〒344-0000 埼玉県 春日部市牛島626 (牛島野球場南側) 施設情報") == "埼玉県春日部市牛島626"
    assert ex.clean_address("春日部市 牛島626") == "春日部市牛島626"
    assert ex.looks_like_address("春日井市美濃町") and not ex.looks_like_address("新狭山公園クラブハウス")


def test_table_column_that_is_not_an_address_is_ignored():  # 狭山市: 『場所』の列が管理事務所の名前
    html = """<html><head><title>野球場|サンプル市</title></head><body><h1>野球場</h1><table>
    <tr><th>施設名</th><th>場所</th></tr><tr><td>テニスコート</td><td>新狭山公園クラブハウス</td></tr></table></body></html>"""
    r = ex.extract_page(html, "サンプル市", SPEC)
    assert all(not i["address"] for i in r["items"])


def test_contact_blocks_are_not_facilities_and_dept_is_cleaned():  # 上里町・坂戸市・熊谷市
    html = """<html><head><title>中央運動場|サンプル市</title></head><body><h1>中央運動場</h1>
    <table><tr><th>所在地</th><td>サンプル市中央1-1</td></tr><tr><th>電話</th><td>0742-11-1111</td></tr></table>
    <h2>このページに関するお問い合わせ先</h2><dl><dt>担当</dt><dd>スポーツ課</dd><dt>電話</dt><dd>0742-99-9999</dd></dl>
    <div>お問い合わせ スポーツ課 スポーツ施設担当 所在地:〒344-8577 サンプル市中央7-2-1 電話 0742-99-9999</div></body></html>"""
    r = ex.extract_page(html, "サンプル市", SPEC)
    assert [(i["name"], i["address"], i["phone"]) for i in r["items"]] == [("中央運動場", "サンプル市中央1-1", "0742-11-1111")]
    assert r["inquiry"]["phone"] == "0742-99-9999" and r["inquiry"]["dept"] == "スポーツ課 スポーツ施設担当"


def test_address_must_start_with_a_municipality_and_not_be_a_sentence():  # v3: 『・』『住』『を有しない者が…』『(代表)』を住所にしない
    for bad in ["・", "住", "(代表)", "を有しない者が過半数利用する場合は、使用料が2倍になります。", "郵便番号:470-0162", "葛和田サッカー場:"]:
        assert not ex.looks_like_address(bad), bad
    for good in ["春日井市美濃町", "深谷市本田501番地先", "埼玉県春日部市牛島626", "〒491-8501 愛知県一宮市本町2丁目5番6号"]:
        assert ex.looks_like_address(good), good


def test_department_heading_with_address_is_not_a_facility():  # 大口町『生涯学習課』
    html = """<html><head><title>多目的広場/サンプル市</title></head><body><h1>多目的広場</h1>
    <h2>生涯学習課</h2><dl><dt>所在地</dt><dd>サンプル市下小口六丁目150番地</dd><dt>電話</dt><dd>0587-95-9033</dd></dl></body></html>"""
    r = ex.extract_page(html, "サンプル市", SPEC)
    assert all(i["name"] != "生涯学習課" for i in r["items"])


def test_trailing_open_parenthesis_is_removed():  # 豊川市『三上町東畑19(』
    assert ex.clean_address("三上町東畑19(地図)") == "三上町東畑19"
    assert ex.clean_address("三上町東畑19 (豊川市)") == "三上町東畑19"
