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
    assert on["schedule"] == [{"cron": "23 20 * * 5"}]  # 金曜20:23 UTC = 土曜05:23 JST
    assert "workflow_dispatch" in on
    pref = wf["weekly-batch"]["jobs"]["prefecture"]
    assert pref["uses"] == "./.github/workflows/weekly-prefecture.yml" and pref["strategy"]["max-parallel"] == 12 and pref["strategy"]["fail-fast"] is False
    jobs = wf["weekly-prefecture"]["jobs"]
    assert jobs["survey_facility"]["uses"] == "./.github/workflows/survey.yml"
    assert jobs["survey_facility"]["with"]["read_pdf"] == "1" and jobs["survey_facility"]["with"]["ocr_pdf"] == "1"
    assert jobs["survey_event"]["with"]["event_focus"] == "1"
    assert jobs["extract"]["uses"] == "./.github/workflows/extract.yml" and jobs["extract"]["with"]["survey_set"] == "weekly_facility"
    # 同じサイトに同時にアクセスしない(1ホスト1リクエスト/秒以下。D-159): 県の中は順番
    assert jobs["survey_event"]["needs"] == "survey_facility" and set(jobs["extract"]["needs"]) == {"survey_facility", "survey_event"} and set(jobs["events"]["needs"]) == {"survey_facility", "survey_event", "extract"}
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


def test_report_handles_unsurveyed_municipalities(tmp_path):
    """初回の実行で、調査できなかった自治体(no_seed等)があるとレポートが KeyError で落ちた(D-155)。"""
    src = ROOT / "data/survey/grandgolf/pdf4_fukui"
    if not src.exists():
        return
    dst = tmp_path / "data/survey/grandgolf/weekly_pdf_fukui"
    shutil.copytree(src, dst)
    f = sorted(dst.glob("*/*.json"))[0]
    d = json.loads(f.read_text(encoding="utf-8"))
    d["outcome"] = "no_seed"
    d["stopped"] = "max_requests"
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    text = report_mod.build(CFG, "2026-11-14", tmp_path)
    assert "調査できなかった内訳: no_seed 1" in text


def test_detail_stages_use_latest_branch_and_tolerate_no_pages():
    """同じ実行の中で調査がコミットした結果を、施設・イベントの取り出しが使う(初回は起動時点のコミットを取得して、結果が無く全県失敗した。D-155)。"""
    for name in ("extract", "events"):
        wf = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"))
        first = wf["jobs"][name]["steps"][0]
        assert first["uses"].startswith("actions/checkout") and first["with"]["ref"] == "${{ github.ref_name }}"
        text = (ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8")
        assert "if-no-files-found: ignore" in text and "if [ -d collected ]" in text


def test_details_only_skips_surveys():
    wf = yaml.safe_load((ROOT / ".github/workflows/weekly-prefecture.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert "details_only" in (wf.get("on") or wf.get(True))["workflow_call"]["inputs"]
    assert "details_only" in jobs["survey_facility"]["if"] and "details_only" in jobs["survey_event"]["if"]
    assert "skipped" in jobs["extract"]["if"] and "skipped" in jobs["events"]["if"]
    batch = yaml.safe_load((ROOT / ".github/workflows/weekly-batch.yml").read_text(encoding="utf-8"))
    assert "details_only" in (batch.get("on") or batch.get(True))["workflow_dispatch"]["inputs"]
    assert batch["jobs"]["prefecture"]["with"]["details_only"] == "${{ inputs.details_only }}"


def test_weekly_diff(tmp_path):
    diff_mod = load("weekly_diff")
    prev, new = tmp_path / "prev", tmp_path / "new"
    prev.mkdir(), new.mkdir()

    def w(d, name, rows):
        import csv
        with open(d / name, "w", encoding="utf-8-sig", newline="") as f:
            cw = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            cw.writeheader()
            cw.writerows(rows)

    r = lambda code, url, pref="福井県", name="X市": {"prefecture": pref, "municipality_code": code, "municipality_name": name, "page_url": url}
    w(prev, "grandgolf_places.csv", [r("1", "u1"), r("2", "u2", name="Y町")])
    w(new, "grandgolf_places.csv", [r("1", "u1"), r("3", "u3", name="Z村"), r("3", "u3b", name="Z村")])
    text = diff_mod.build(prev, new, tmp_path / "out")
    assert "新しく 1、無くなった 1" in text and "福井県Z村" in text and "福井県Y町" in text
    added = (tmp_path / "out/grandgolf_places_new.csv").read_text(encoding="utf-8-sig")
    assert "u3" in added and "u1" not in added
    assert "前週のCSVが無い" in diff_mod.build(tmp_path / "none", new, tmp_path / "o2")
    wf = (ROOT / ".github/workflows/weekly-batch.yml").read_text(encoding="utf-8")
    assert "prev/event_focus" in wf and "--list event" in wf
    assert "cp data/export/weekly/*.csv prev/" in wf and "scripts/weekly_diff.py" in wf and wf.index("cp data/export/weekly/*.csv prev/") < wf.index("survey-export")


def test_discovery_options_flow_from_config_to_cli():
    """発見を増やす設定(PDF40件・外部サイト)が、設定 → 計画 → ワークフロー → CLI までつながっている(D-161)。"""
    assert CFG["facility_max_pdfs"] == 40 and CFG["follow_external"] is True
    t = plan_mod.plan("config/weekly_batch.json", "福井県")[0][0]
    assert t["facility_max_pdfs"] == "40" and t["follow_external"] == "1"
    pref = yaml.safe_load((ROOT / ".github/workflows/weekly-prefecture.yml").read_text(encoding="utf-8"))["jobs"]
    assert pref["survey_facility"]["with"]["max_pdfs"] == "${{ inputs.facility_max_pdfs }}" and pref["survey_facility"]["with"]["follow_external"] == "${{ inputs.follow_external }}"
    assert "follow_external" not in pref["survey_event"]["with"]  # イベント探索は外部サイトを見ない(重複を避ける)
    batch = yaml.safe_load((ROOT / ".github/workflows/weekly-batch.yml").read_text(encoding="utf-8"))["jobs"]["prefecture"]["with"]
    assert batch["follow_external"] == "${{ matrix.follow_external }}" and batch["facility_max_pdfs"] == "${{ matrix.facility_max_pdfs }}"
    survey = (ROOT / ".github/workflows/survey.yml").read_text(encoding="utf-8")
    assert "--follow-external" in survey and '--max-pdfs "${MAX_PDFS:-20}"' in survey
