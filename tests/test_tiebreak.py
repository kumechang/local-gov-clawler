"""v12.1 同点のタイブレーク(D-103/D-104)。ユーザーが判断した例(出雲市・一宮市・太良町・読谷村)を再現する。"""
from localgov_crawler import hub
from localgov_crawler.redecide import redecide


def c(url, text, kind, score=20, fl=8, depth=2):
    return hub.Candidate(url, text, score, reasons=[], depth=depth, facility_link_count=fl, fetched=True, kind=kind, page_title=text)


def test_t1_listing_word_wins_among_ties():  # 出雲市
    d = hub.decide([c("https://x.jp/a/1/index.html", "スポーツ施設一覧", "sports_pure", 28), c("https://x.jp/b/2/index.html", "スポーツ施設", "sports_pure", 27), c("https://x.jp/b/3/index.html", "スポーツ施設", "sports_pure", 27)])
    assert d.outcome == "hub_selected" and d.selected.text == "スポーツ施設一覧"


def test_t1_not_applied_when_all_have_listing_word():
    d = hub.decide([c("https://x.jp/a", "スポーツ施設一覧", "sports_pure", 20), c("https://x.jp/b", "体育施設一覧", "sports_pure", 20)])
    assert d.outcome == "hub_multiple"


def test_t2_parent_over_children():  # 一宮市
    d = hub.decide([c("https://x.jp/shisetsu/100/index.html", "スポーツ施設", "sports_pure", 24, 4), c("https://x.jp/shisetsu/100/101/index.html", "屋内スポーツ施設", "sports_other", 23, 7)])
    assert d.outcome == "hub_selected" and d.selected.url.endswith("/100/index.html")


def test_t2_siblings_stay_multiple():  # 日の出町型(別々の分類の下)
    d = hub.decide([c("https://x.jp/c/1", "体育施設", "sports_pure", 22, 5), c("https://x.jp/c/2", "スポーツ施設", "sports_pure", 21, 4)])
    assert d.outcome == "hub_multiple"


def test_t4_sentence_label_loses():  # 読谷村
    d = hub.decide([c("https://x.jp/a/2643.html", "社会体育施設・学校体育施設の利用について", "sports_pure", 18, 7), c("https://x.jp/b/taiikushisetsu/index.html", "読谷村体育施設", "sports_pure", 18, 4)])
    assert d.outcome == "hub_selected" and d.selected.text == "読谷村体育施設"


def _tara_result():
    a = c("https://x.jp/koukyou/_1322.html", "B&G海洋センター体育館", "sports_other", 19, 10)
    b = c("https://x.jp/koukyou/_1331.html", "B&G海洋センター第2体育館", "sports_other", 19, 10)
    g = c("https://x.jp/koukyou.html", "公共施設利用案内", "generic", 14, 10)
    pc = {"of": a.url, "fetched": True, "page_title": "公共施設利用案内 | 太良町", "facility_link_count": 10, "parent_url": g.url, "final_url": g.url, "facility_samples": []}
    return a, b, g, pc


def test_t3_generic_parent_for_tied_facility_pages():  # 太良町
    a, b, g, pc = _tara_result()
    d = hub.decide([a, b, g])
    assert d.outcome == "hub_multiple"
    d2 = hub.ascend(d, pc)
    assert d2.outcome == "hub_selected" and d2.selected.url == g.url and d2.quality == "generic"


def test_t3_not_for_reservation_title_or_few_links():
    a, b, g, pc = _tara_result()
    d = hub.decide([a, b, g])
    assert hub.ascend(d, {**pc, "page_title": "公共施設予約 | 太良町"}).outcome == "hub_multiple"
    assert hub.ascend(d, {**pc, "facility_link_count": 2}).outcome == "hub_multiple"


def test_t3_not_applied_to_already_selected():
    a = c("https://x.jp/koukyou/_1322.html", "B&G海洋センター体育館", "sports_other", 19, 10)
    pc = {"of": a.url, "fetched": True, "page_title": "公共施設利用案内 | 太良町", "facility_link_count": 10, "parent_url": "https://x.jp/koukyou.html"}
    d = hub.decide([a])
    assert d.outcome == "hub_selected" and hub.ascend(d, pc).selected.url == a.url


def test_redecide_rebuilds_outcome_from_stored_candidates():
    cands = [c("https://x.jp/a/1/index.html", "スポーツ施設一覧", "sports_pure", 28), c("https://x.jp/b/2/index.html", "スポーツ施設", "sports_pure", 27)]
    old = {
        "run": {"route": "old"}, "outcome": "hub_multiple", "needs_review": ["hub_multiple"], "ai_needed": True, "site_profile": {"rendering": {"needs_headless": False}},
        "genre_entrypoints": [{"decision": "hub_multiple", "quality": "specific", "selected": None, "candidates": [x.to_dict() for x in cands], "parent_check": None}],
    }
    new = redecide(old, "new", "v12.1")
    assert new["outcome"] == "hub_selected" and new["needs_review"] == [] and new["ai_needed"] is False
    assert new["run"]["route"] == "new" and new["run"]["redecided_from"] == "old"
    assert new["genre_entrypoints"][0]["selected"]["text"] == "スポーツ施設一覧"
    assert old["outcome"] == "hub_multiple"  # 元は変えない


def test_same_page_with_different_scheme_is_not_a_tie():  # 大磯町: httpとhttpsの同じページ
    d = hub.decide([c("http://www.x.jp/shisetsu/sports/index.html", "スポーツ施設・プール・海水浴場", "sports_other", 17), c("https://www.x.jp/shisetsu/sports/index.html", "スポーツ施設・プール・海水浴場", "sports_other", 17)])
    assert d.outcome == "hub_selected"


def test_t1_ignores_composite_labels():  # 栄町: 『連絡先一覧』
    d = hub.decide([c("https://x.jp/a", "文化・スポーツ施設 -連絡先一覧-", "sports_composite", 24, 8), c("https://x.jp/b", "文化・スポーツ施設 -施設-", "sports_composite", 22, 8)])
    assert d.outcome != "hub_selected" or "連絡先" not in d.selected.text


def test_t3_not_for_category_pages():  # 釧路市: 『公園・スポーツ施設』などの分類ページが並ぶ
    a = c("https://x.jp/s/1.html", "公園・スポーツ施設", "sports_other", 27, 9)
    b = c("https://x.jp/s/2.html", "無料施設 その他スポーツ施設", "sports_other", 26, 9)
    g = c("https://x.jp/s/", "公共施設一覧", "generic", 20, 11)
    d = hub.decide([a, b, g])
    pc = {"of": a.url, "fetched": True, "page_title": "公共施設一覧 | x", "facility_link_count": 11, "parent_url": g.url, "final_url": g.url}
    assert d.outcome == "hub_multiple" and hub.ascend(d, pc).outcome == "hub_multiple"


def test_t2_bare_sports_parent_stays_multiple():  # 千代田区・岡谷市: 『スポーツ』だけの親は採らない(D-105)
    d = hub.decide([c("https://x.jp/sports/index.html", "スポーツ", "sports_pure", 14, 4), c("https://x.jp/sports/riyo.html", "スポーツ施設利用補助", "sports_other", 17, 3)])
    assert d.outcome == "hub_multiple"
