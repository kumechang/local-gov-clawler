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


def test_address_without_a_city_name_in_the_address_field_is_kept():  # 上尾市『西門前580-1』
    assert ex.clean_address("/西門前580-1、敷地面積/約0.7ヘクタール") == "西門前580-1"
    assert ex.looks_like_address("/西門前580-1、敷地面積/約0.7ヘクタール")
    assert ex.clean_address("緑浜町2-3、5-1") == "緑浜町2-3、5-1"  # 複数の地番の読点は切らない
    assert not ex.looks_like_address("葛和田サッカー場:") and not ex.looks_like_address("住") and not ex.looks_like_address("・")


def test_facility_name_is_tidied():
    assert ex.tidy_name("施設案内 横須賀公園") == "横須賀公園"
    assert ex.tidy_name("『桶川市新小針領家グラウンド』について") == "桶川市新小針領家グラウンド"
    assert ex.tidy_name("上平広場の利用について") == "上平広場"
    assert ex.tidy_name("中央公園グラウンド ナイター") == "中央公園グラウンド ナイター"


def test_tidy_export_fields():
    from localgov_crawler.extract import keep_item, tidy_export_address, tidy_export_dept

    assert tidy_export_address("階上町大字道仏字天当平1-150(", "階上町") == "階上町大字道仏字天当平1-150"
    assert tidy_export_address("太田市", "太田市") == ""
    assert tidy_export_address("西門前580-1", "上尾市") == "西門前580-1"
    assert tidy_export_dept("栃木市役所 法人番号 6000020092037 適格請求書発行事業者登録番号 T6000020092037") == "栃木市役所"
    assert not keep_item("階上町 Official Web Site", "", "0178-32-0147")
    assert not keep_item("お問合せ", "府中市", "")


def test_table_caption_keyword_and_dedupe():
    from localgov_crawler.extract import detail_rows, extract_page
    spec = SPEC
    html = ("<html><body><h1>スポーツ施設</h1><h2>ニュースポーツ競技場一覧(グラウンドゴルフなど)</h2>"
            "<table><tr><th>施設名</th><th>住所</th><th>電話</th></tr>"
            "<tr><td>南部ふるさと広場</td><td>野尻町1373-6</td><td>0853-48-0001</td></tr></table>"
            "<h2>体育館</h2><table><tr><th>施設名</th><th>住所</th><th>電話</th></tr>"
            "<tr><td>出雲体育館</td><td>出雲市今市町1</td><td>0853-21-0001</td></tr></table></body></html>")
    pg = extract_page(html, "出雲市", spec)
    flags = {i["name"]: i["keyword_in_item"] for i in pg["items"]}
    assert flags["南部ふるさと広場"] and not flags["出雲体育館"]
    rec = {"municipality": {"prefecture": "島根県", "code": "32203", "name": "出雲市", "official_url": ""}, "run": {"route": "t", "finished_at": ""},
           "pages": [{**pg, "page_url": "u", "title": "t", "matched_text": ""}, {**pg, "page_url": "u", "title": "t", "matched_text": ""}]}
    rows = detail_rows(rec)
    assert len(rows) == 1 and rows[0]["facility_name"] == "南部ふるさと広場"


def test_page_level_text_row_dropped_when_specific_row_exists():
    from localgov_crawler.extract import detail_rows

    m = {"prefecture": "石川県", "code": "17210", "name": "かほく市", "official_url": ""}
    cat = {"page_url": "a", "title": "t", "page_name": "スポーツ・レジャー施設", "multi_facility": False, "matched_text": "",
           "items": [{"name": "スポーツ・レジャー施設", "address": "", "phone": "076-283-1111", "source": "text", "keyword_in_item": False}]}
    det = {"page_url": "b", "title": "t", "page_name": "高松グラウンド・ゴルフ場", "multi_facility": False, "matched_text": "",
           "items": [{"name": "高松グラウンド・ゴルフ場", "address": "かほく市二ツ屋マ1番地", "phone": "076-281-3751", "source": "kv", "keyword_in_item": True}]}
    rows = detail_rows({"municipality": m, "run": {"route": "t", "finished_at": ""}, "pages": [cat, det]})
    assert [r["facility_name"] for r in rows] == ["高松グラウンド・ゴルフ場"]
    rows = detail_rows({"municipality": m, "run": {"route": "t", "finished_at": ""}, "pages": [cat]})
    assert len(rows) == 1  # 別に施設の行が無ければ、そのまま残す


def test_phone_with_dash_variants_and_office_name():
    from localgov_crawler.extract import find_phones, keep_item

    assert find_phones("電話番号：0296‐88‐3111 ファクス番号：0296−88−3253") == ["0296-88-3111", "0296-88-3253"]
    assert find_phones("TEL 0296ー88ー3111") == ["0296-88-3111"]
    assert find_phones("郵便番号 311-4402 電話 029-288-3111") == ["029-288-3111"]
    assert not keep_item("東員町役場", "三重県員弁郡東員町大字山田1600番地", "0594-86-2800")


def test_inquiry_by_heading_bullet_items_and_name_only_table():
    from localgov_crawler.extract import extract_page

    h = ("<html><body><main><h1>東公園グラウンドの施設案内</h1><table><tr><td>所在地</td><td>福井市豊島2丁目5-26</td></tr>"
         "<tr><td>施設概要</td><td>グラウンドゴルフなど</td></tr></table>"
         "<h3>お問い合わせ先</h3><p>商工労働部観光文化スポーツ局 <a href='#'>スポーツ課</a><br><span>電話番号 </span>0776-20-5355 ｜ FAX 0776-20-5670<br>〒910-0004 福井市宝永2丁目4番10号</p>"
         "</main></body></html>")
    pg = extract_page(h, "福井市", SPEC)
    assert pg["inquiry"] == {"dept": "商工労働部観光文化スポーツ局 スポーツ課", "phone": "0776-20-5355"}

    h = ("<html><body><h1>スポーツ施設</h1><h2>グラウンドゴルフ場</h2><p>・蔵木グラウンドゴルフ場吉賀町蔵木６０-２</p><p>　コース：８ホール</p><p>　【問い合わせ】電話0856-77-0633</p>"
         "<p>・大野原グラウンドゴルフ場吉賀町大野原９６９</p><p>　【問い合わせ】電話0856-79-2330</p></body></html>")
    pg = extract_page(h, "吉賀町", SPEC)
    assert [(i["name"], i["address"], i["phone"]) for i in pg["items"]] == [
        ("蔵木グラウンドゴルフ場", "吉賀町蔵木60-2", "0856-77-0633"), ("大野原グラウンドゴルフ場", "吉賀町大野原969", "0856-79-2330")]

    h = ("<html><body><h1>スポーツ施設(市町村別)</h1><table><caption>御代田町のスポーツ施設</caption><tr><th>名称</th><th>種別</th><th>内容</th></tr>"
         "<tr><td>やまゆり公園マレットゴルフ場</td><td>マレットゴルフ場</td><td>36ホール</td></tr>"
         "<tr><td>やまゆり公園グラウンドゴルフ場</td><td>グラウンドゴルフ場</td><td></td></tr></table></body></html>")
    pg = extract_page(h, "佐久市", SPEC)
    flags = {i["name"]: i["keyword_in_item"] for i in pg["items"]}
    assert flags == {"やまゆり公園マレットゴルフ場": False, "やまゆり公園グラウンドゴルフ場": True}


def test_bullet_needs_facility_suffix_and_name_only_table_is_a_last_resort():
    from localgov_crawler.extract import extract_page

    h = "<html><body><h1>野球場</h1><h2>運営</h2><p>・施設の管理運営・スポーツ教室豊中市服部寿町4-7</p><p>電話 06-6858-5050</p></body></html>"
    assert not [i for i in extract_page(h, "豊中市", SPEC)["items"] if i["source"] == "bullet"]
    h = ("<html><body><h1>公園</h1><table><tr><th>名称</th><th>種別</th></tr><tr><td>A広場</td><td>広場</td></tr></table>"
         "<table><tr><th>所在地</th><td>丹波市山南町和田338</td></tr><tr><th>電話</th><td>0795-76-1345</td></tr></table></body></html>")
    pg = extract_page(h, "丹波市", SPEC)
    assert [(i["name"], i["address"], i["source"]) for i in pg["items"]] == [("公園", "丹波市山南町和田338", "kv+text_phone")] or all(i["source"] != "table_name" for i in pg["items"])
