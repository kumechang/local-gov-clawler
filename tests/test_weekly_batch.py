import importlib.util
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan_mod = load("plan_weekly_batch")
report_mod = load("weekly_report")
CFG = json.loads((ROOT / "config/weekly_batch.json").read_text(encoding="utf-8"))


def test_config_covers_47_prefectures_and_all_municipalities():
    from localgov_crawler import municipalities as mun
    prefs = CFG["prefectures"]
    assert len(prefs) == 47 and len({p["slug"] for p in prefs}) == 47 and len({p["name"] for p in prefs}) == 47
    items = mun.select(mun.load(mun.DEFAULT_MASTER), None, None, None, "municipality")
    names = {m.prefecture_name for m in items}
    assert names == {p["name"] for p in prefs}
    # シャードは自治体数÷50(切り上げ)以上。1シャードが長すぎてジョブの上限(350分)を超えないように
    for p in prefs:
        n = sum(1 for m in items if m.prefecture_name == p["name"])
        assert p["shards"] * 50 >= n, p


def test_survey_sets_match_config():
    fac = json.loads((ROOT / "config/survey_sets/weekly_facility.json").read_text(encoding="utf-8"))["routes"]
    ev = json.loads((ROOT / "config/survey_sets/weekly_events.json").read_text(encoding="utf-8"))["routes"]
    assert fac == report_mod.routes(CFG, "facility")
    assert ev == report_mod.routes(CFG, "event") + fac
    assert all(r.startswith("weekly_") for r in fac + ev)


def test_plan_all_and_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    targets, notes = plan_mod.plan("config/weekly_batch.json")
    assert len(targets) == 47 and notes == []
    t = next(x for x in targets if x["slug"] == "fukui")
    assert t["facility_route"] == "weekly_pdf_fukui" and t["event_route"] == "weekly_ev_fukui" and t["detail_route"] == "weekly_fukui" and t["from_route"] == "redecide_v12_1"
    assert [x["slug"] for x in plan_mod.plan("config/weekly_batch.json", "福井県")[0]] == ["fukui"]
    assert [x["slug"] for x in plan_mod.plan("config/weekly_batch.json", "fukui")[0]] == ["fukui"]
    assert plan_mod.plan("config/weekly_batch.json", "どこか")[0] == []
    off = tmp_path / "off.json"
    off.write_text(json.dumps({**CFG, "enabled": False}, ensure_ascii=False), encoding="utf-8")
    assert plan_mod.plan(str(off))[0] == []


def test_workflows_are_wired():
    wf = {n: yaml.safe_load((ROOT / f".github/workflows/{n}.yml").read_text(encoding="utf-8")) for n in ("weekly-batch", "weekly-prefecture", "extract")}
    on = wf["weekly-batch"].get("on") or wf["weekly-batch"].get(True)
    assert on["schedule"] == [{"cron": "0 21 * * 5"}]  # 金曜21:00 UTC = 土曜06:00 JST
    assert "workflow_dispatch" in on
    pref = wf["weekly-batch"]["jobs"]["prefecture"]
    assert pref["uses"] == "./.github/workflows/weekly-prefecture.yml" and pref["strategy"]["max-parallel"] == 12 and pref["strategy"]["fail-fast"] is False
    jobs = wf["weekly-prefecture"]["jobs"]
    assert jobs["survey_facility"]["uses"] == "./.github/workflows/survey.yml"
    assert jobs["survey_facility"]["with"]["read_pdf"] == "1" and jobs["survey_facility"]["with"]["ocr_pdf"] == "1"
    assert jobs["survey_event"]["with"]["event_focus"] == "1"
    assert jobs["extract"]["uses"] == "./.github/workflows/extract.yml" and jobs["extract"]["with"]["survey_set"] == "weekly_facility"
    assert jobs["events"]["uses"] == "./.github/workflows/events.yml" and jobs["events"]["with"]["survey_set"] == "weekly_events"
    # 結果をコミットする(定期実行はmainへ)
    assert all(j["with"]["commit_results"] is True and j["permissions"]["contents"] == "write" for j in jobs.values())
    on_ext = wf["extract"].get("on") or wf["extract"].get(True)
    assert "survey_set" in on_ext["workflow_call"]["inputs"] and "survey_set" in on_ext["workflow_dispatch"]["inputs"]


def test_weekly_routes_do_not_collide_with_auto_runs():
    """auto-* は『結果がある route は実行しない』ので、weekly_* の名前を使うと自動実行が止まる。重ならないこと。"""
    auto = json.loads((ROOT / "config/auto_survey.json").read_text(encoding="utf-8"))
    assert not any(t["route"].startswith("weekly_") for t in auto["targets"])
    # 保存先が 1 route = 1 県なので、artifact名(…-<route>-<shard>)が県をまたいで衝突しない
    routes = report_mod.routes(CFG, "facility") + report_mod.routes(CFG, "event")
    assert len(routes) == len(set(routes)) == 94


def test_pdf_rows_are_not_refetched_as_html():
    from localgov_crawler import cli
    assert "pdf" in cli.PDF_FOUND_VIA and "pdf_link" in cli.PDF_FOUND_VIA
    src = (ROOT / "src/localgov_crawler/cli.py").read_text(encoding="utf-8")
    assert src.count('not in PDF_FOUND_VIA') == 2 and 'found_via"] != "pdf_link"' not in src


def test_report_builds_from_stored_surveys(tmp_path):
    src = ROOT / "data/survey/grandgolf/pdf4_fukui"
    if not src.exists():
        return
    shutil.copytree(src, tmp_path / "data/survey/grandgolf/weekly_pdf_fukui")
    text = report_mod.build(CFG, "2026-11-07", tmp_path)
    assert "2026-11-07" in text and "PDF+OCRつき" in text and "結果がある自治体: 17 / 対象 1747" in text
    assert "施設の詳細" in text and "イベントの詳細" in text
