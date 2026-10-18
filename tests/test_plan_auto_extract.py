import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
SPEC = importlib.util.spec_from_file_location("plan_auto_extract", ROOT / "scripts" / "plan_auto_extract.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_plan_skips_existing_and_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    (tmp_path / "grandgolf" / "r1").mkdir(parents=True)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"enabled": True, "targets": [{"prefecture": "愛知県", "keyword": "grandgolf", "route": "r1"}, {"prefecture": "福井県", "keyword": "grandgolf", "route": "r2", "shards": 2}]}, ensure_ascii=False), encoding="utf-8")
    targets, notes = mod.plan(str(cfg), str(tmp_path), "x")
    assert [t["route"] for t in targets] == ["r2"] and targets[0]["shards"] == "2"
    assert mod.plan(str(cfg), str(tmp_path), "x [skip extract]")[0] == []


def test_extract_workflows_are_wired():
    for n in ("extract", "auto-extract"):
        yaml.safe_load((ROOT / f".github/workflows/{n}.yml").read_text(encoding="utf-8"))
    ex = (ROOT / ".github/workflows/extract.yml").read_text(encoding="utf-8")
    assert "extract-${{ inputs.keyword }}-${{ inputs.route }}-${{ matrix.shard }}" in ex and "pattern: extract-${{ inputs.keyword }}-${{ inputs.route }}-*" in ex
    assert "config/survey_sets/$KEYWORD.json" in ex and "--headless" in ex
    auto = yaml.safe_load((ROOT / ".github/workflows/auto-extract.yml").read_text(encoding="utf-8"))
    assert auto["jobs"]["extract"]["uses"] == "./.github/workflows/extract.yml"
    assert (ROOT / "config/survey_sets/grandgolf.json").exists() and (ROOT / "config/auto_extract.json").exists()
