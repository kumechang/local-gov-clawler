from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def test_artifact_names_include_route():
    """auto-crawl は複数の県を同じ実行で並列に動かすので、artifact名が衝突しないよう route を含める(v7で奈良県が福井県の結果を拾った)。"""
    text = (ROOT / ".github/workflows/crawl.yml").read_text(encoding="utf-8")
    assert "name: results-${{ inputs.route }}-${{ matrix.shard }}" in text
    assert "name: raw-html-${{ inputs.route }}-${{ matrix.shard }}" in text
    assert "pattern: results-${{ inputs.route }}-*" in text
    assert "name: crawl-sqlite-${{ inputs.route }}" in text
    # 「results-0」のような route を含まない名前が残っていない
    assert "name: results-${{ matrix.shard }}" not in text and "pattern: results-*" not in text


def test_workflows_are_valid_yaml_and_auto_crawl_calls_crawl():
    for name in ("crawl", "auto-crawl", "ci"):
        yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"))
    auto = yaml.safe_load((ROOT / ".github/workflows/auto-crawl.yml").read_text(encoding="utf-8"))
    assert auto["jobs"]["crawl"]["uses"] == "./.github/workflows/crawl.yml"
    crawl = yaml.safe_load((ROOT / ".github/workflows/crawl.yml").read_text(encoding="utf-8"))
    assert "workflow_call" in (crawl.get("on") or crawl.get(True))


def test_scope_and_compact_flow_from_auto_crawl_to_cli():
    crawl = (ROOT / ".github/workflows/crawl.yml").read_text(encoding="utf-8")
    assert '--scope "$SCOPE"' in crawl and "--compact" in crawl
    auto = (ROOT / ".github/workflows/auto-crawl.yml").read_text(encoding="utf-8")
    assert "scope: ${{ matrix.scope }}" in auto and "compact: ${{ matrix.compact }}" in auto


def test_code_flows_from_auto_crawl_to_cli():
    crawl = (ROOT / ".github/workflows/crawl.yml").read_text(encoding="utf-8")
    auto = (ROOT / ".github/workflows/auto-crawl.yml").read_text(encoding="utf-8")
    assert '--code "$CODE"' in crawl and "code: ${{ matrix.code }}" in auto


def test_survey_workflows_are_valid_and_wired():
    for name in ("survey", "auto-survey"):
        yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"))
    survey = (ROOT / ".github/workflows/survey.yml").read_text(encoding="utf-8")
    assert "name: survey-${{ inputs.keyword }}-${{ inputs.route }}-${{ matrix.shard }}" in survey
    assert "pattern: survey-${{ inputs.keyword }}-${{ inputs.route }}-*" in survey
    auto = yaml.safe_load((ROOT / ".github/workflows/auto-survey.yml").read_text(encoding="utf-8"))
    assert auto["jobs"]["survey"]["uses"] == "./.github/workflows/survey.yml"
    cfg = (ROOT / "config/auto_survey.json").read_text(encoding="utf-8")
    assert "grandgolf" in cfg and (ROOT / "config/keywords/grandgolf.json").exists()
