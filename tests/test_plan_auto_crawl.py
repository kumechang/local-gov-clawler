import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("plan_auto_crawl", Path(__file__).parent.parent / "scripts" / "plan_auto_crawl.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def write_cfg(tmp_path, **kw):
    cfg = {"enabled": True, "targets": [{"prefecture": "奈良県", "route": "r1"}, {"prefecture": "福井県", "route": "r2"}]}
    cfg.update(kw)
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_all_targets_when_routes_unused(tmp_path):
    (tmp_path / "results").mkdir()
    targets, _ = mod.plan(write_cfg(tmp_path), str(tmp_path / "results"), "feat: x")
    assert [t["route"] for t in targets] == ["r1", "r2"]


def test_existing_route_is_not_overwritten(tmp_path):
    (tmp_path / "results" / "r1").mkdir(parents=True)
    targets, notes = mod.plan(write_cfg(tmp_path), str(tmp_path / "results"), "")
    assert [t["route"] for t in targets] == ["r2"] and any("r1" in n for n in notes)


def test_disabled_or_skip_marker_runs_nothing(tmp_path):
    (tmp_path / "results").mkdir()
    assert mod.plan(write_cfg(tmp_path, enabled=False), str(tmp_path / "results"), "")[0] == []
    assert mod.plan(write_cfg(tmp_path), str(tmp_path / "results"), "docs only [skip crawl]")[0] == []


def test_real_config_is_valid():
    cfg = json.loads((Path(__file__).parent.parent / "config" / "auto_crawl.json").read_text(encoding="utf-8"))
    assert all({"prefecture", "route"} <= set(t) for t in cfg["targets"])
    routes = [t["route"] for t in cfg["targets"]]
    assert len(routes) == len(set(routes))


def test_scope_and_compact_are_passed_through_with_defaults(tmp_path):
    (tmp_path / "results").mkdir()
    cfg = write_cfg(tmp_path, targets=[{"prefecture": "愛知県", "route": "r1", "scope": "municipality", "compact": True}, {"prefecture": "福井県", "route": "r2"}])
    targets, _ = mod.plan(cfg, str(tmp_path / "results"), "")
    assert targets[0]["scope"] == "municipality" and targets[0]["compact"] is True
    assert targets[1]["scope"] == "" and targets[1]["compact"] is False


def test_code_is_passed_through_with_default(tmp_path):
    cfg = write_cfg(tmp_path, targets=[{"prefecture": "和歌山県", "route": "r1", "code": "30381"}, {"prefecture": "福井県", "route": "r2"}])
    targets, _ = mod.plan(str(cfg), str(tmp_path / "results"), "x")
    assert targets[0]["code"] == "30381" and targets[1]["code"] == ""
