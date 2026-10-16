import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
SPEC = importlib.util.spec_from_file_location("plan_auto_survey", ROOT / "scripts" / "plan_auto_survey.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def cfg(tmp_path, **kw):
    c = {"enabled": True, "targets": [{"prefecture": "愛知県", "keyword": "grandgolf", "route": "r1"}, {"prefecture": "福井県", "keyword": "grandgolf", "route": "r2", "shards": 2}]}
    c.update(kw)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_plan_defaults_and_skips(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    survey = tmp_path / "survey"
    (survey / "grandgolf" / "r1").mkdir(parents=True)
    targets, notes = mod.plan(cfg(tmp_path), str(survey), "x")
    assert [t["route"] for t in targets] == ["r2"] and targets[0]["shards"] == "2" and targets[0]["from_route"] == "redecide_v12_1" and targets[0]["max_pages"] == "200"
    assert any("r1" in n for n in notes)
    assert mod.plan(cfg(tmp_path), str(survey), "x [skip survey]")[0] == []
    assert mod.plan(cfg(tmp_path, enabled=False), str(survey), "x")[0] == []


def test_unknown_keyword_is_not_run(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    targets, notes = mod.plan(cfg(tmp_path, targets=[{"prefecture": "愛知県", "keyword": "nokeyword", "route": "r"}]), str(tmp_path / "s"), "x")
    assert targets == [] and "nokeyword" in notes[0]
