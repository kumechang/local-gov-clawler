import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import yaml

from localgov_crawler import events as ev
from localgov_crawler import survey as sv

ROOT = Path(__file__).parent.parent
SPEC = sv.KeywordSpec("grandgolf", "グラウンドゴルフ", [re.compile(r"グラウ?ンド[\s・･\-ー]*ゴルフ")])


def test_parse_dates_handles_eras_and_context_year():
    assert ev.parse_dates("令和8年11月21日(土) 午前8時30分", None) == [date(2026, 11, 21)]
    assert ev.parse_dates("2026年6月14日(日曜日)", None) == [date(2026, 6, 14)]
    assert ev.parse_dates("R7.10.5 ~ R7.10.6", None) == [date(2025, 10, 5), date(2025, 10, 6)]
    assert ev.parse_dates("10月5日(日)", 2025) == [date(2025, 10, 5)]
    assert ev.parse_dates("10月5日(日)", None) == []  # 年が分からない月日は日付にしない
    assert ev.parse_dates("令和7年度 ... 2月3日", 2025) == [date(2026, 2, 3)]  # 年度の4月より前の月は翌年
    assert ev.period_of(date(2025, 3, 31), None) == "期間外" and ev.period_of(date(2025, 4, 1), None) == "期間内" and ev.period_of(None, None) == "日付不明"


def test_labeled_lines_numbered_spaced_and_next_line_values():
    body = "1、日時\n令和6年6月16日(日曜日)午前8時30分\n2、場所\n三芳野小学校 校庭\n3 対 象 地区の方\n4 参加費 無料\n5 申込期間 令和8年10月1日から"
    f = ev._labeled_lines(body)
    assert f["date"].startswith("令和6年6月16日") and f["venue"] == "三芳野小学校 校庭" and f["target"] == "地区の方" and f["fee"] == "無料" and f["deadline"].startswith("令和8年10月1日")
    f = ev._labeled_lines("2 日 時 令和8年11月21日(土)\n3 会 場 神野々緑地")
    assert f["date"].startswith("令和8年11月21日") and f["venue"] == "神野々緑地"


def test_single_event_page_calendar_lines_and_table_rows():
    h = ("<html><head><title>令和8年度 親子グラウンドゴルフ大会の開催について/橋本市</title></head><body><main><h1>令和8年度 親子グラウンドゴルフ大会の開催について</h1>"
         "<p>2 日 時 令和8年11月21日(土) 午前8時30分~</p><p>3 会 場 神野々緑地芝生広場</p><p>4 対 象 親子</p><p>7 申込期間 令和8年10月1日から10月30日まで</p>"
         "<p>(電話:0736-33-3704 橋本市教育委員会生涯学習課)</p></main></body></html>")
    r = ev.extract_events(h, "橋本市", SPEC)
    e = r["events"][0]
    assert r["event_kind"] == "グラウンドゴルフ専用" and e["source"] == "page" and e["event_name"].startswith("令和8年度 親子グラウンドゴルフ大会")
    assert e["date_start"] == "2026-11-21" and e["period"] == "期間内" and e["venue"] == "神野々緑地芝生広場" and e["target"] == "親子" and e["deadline"].startswith("令和8年10月1日")

    h = ("<html><head><title>令和8年度大会・イベント情報</title></head><body><main><h1>令和8年度大会・イベント情報</h1><table><tr><th>大会名</th><th>開催日</th><th>会場</th></tr>"
         "<tr><td>第16回ペアグラウンド・ゴルフ大会</td><td>令和8年6月24日</td><td>及川球技場</td></tr><tr><td>テニス大会</td><td>令和8年7月1日</td><td>テニスコート</td></tr></table></main></body></html>")
    r = ev.extract_events(h, "厚木市", SPEC)
    assert [(e["event_name"], e["date_start"], e["venue"], e["source"]) for e in r["events"]] == [("第16回ペアグラウンド・ゴルフ大会", "2026-06-24", "及川球技場", "table_row")]

    h = ("<html><head><title>イベント情報 令和8年度</title></head><body><main><h1>イベント情報</h1><p>6月28日(日)</p><p>親子でグラウンド・ゴルフ体験</p><p>7月1日 そうめん流し</p></main></body></html>")
    r = ev.extract_events(h, "鹿屋市", SPEC)
    assert r["event_kind"] == "カレンダー・予定表" and [(e["event_name"], e["date_start"]) for e in r["events"]] == [("親子でグラウンド・ゴルフ体験", "2026-06-28")]


def test_event_rows_and_columns():
    rec = {"municipality": {"prefecture": "神奈川県", "code": "14216", "name": "厚木市", "official_url": "https://x/"}, "run": {"route": "t", "finished_at": "now"},
           "pages": [{"title": "t", "page_url": "u", "events": [{"event_name": "A", "date_start": "2026-06-24", "period": "期間内", "source": "table_row"}]}]}
    rows = ev.event_rows(rec)
    assert list(rows[0].keys()) == ev.EVENT_COLUMNS and rows[0]["event_name"] == "A" and rows[0]["venue"] == ""


def test_events_workflows_are_wired():
    mod_spec = importlib.util.spec_from_file_location("plan_auto_events", ROOT / "scripts" / "plan_auto_events.py")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    cfg = json.loads((ROOT / "config" / "auto_events.json").read_text(encoding="utf-8"))
    assert len(cfg["targets"]) == 47 and all(t["route"].startswith("ev1_") for t in cfg["targets"])
    for n in ("events", "auto-events"):
        yaml.safe_load((ROOT / f".github/workflows/{n}.yml").read_text(encoding="utf-8"))
    ex = (ROOT / ".github/workflows/events.yml").read_text(encoding="utf-8")
    assert "events-${{ inputs.keyword }}-${{ inputs.route }}-${{ matrix.shard }}" in ex and "events-export" in ex and "data/events" in ex
    auto = yaml.safe_load((ROOT / ".github/workflows/auto-events.yml").read_text(encoding="utf-8"))
    assert auto["jobs"]["events"]["uses"] == "./.github/workflows/events.yml"
