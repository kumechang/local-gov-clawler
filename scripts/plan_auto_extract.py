"""config/auto_extract.json から、自動施設詳細の取り出しの対象(結果が未作成の keyword+route)を決めて、GitHub Actionsの出力に書く。"""
import json
import os
import sys
from pathlib import Path


def plan(config_path: str, survey_dir: str, commit_message: str) -> tuple[list[dict], list[str]]:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    notes: list[str] = []
    if not cfg.get("enabled", False):
        return [], ["config/auto_extract.json の enabled が false のため、実行しない"]
    if "[skip extract]" in commit_message:
        return [], ["コミットメッセージに [skip extract] があるため、実行しない"]
    targets = []
    for t in cfg.get("targets", []):
        keyword, route = t["keyword"], t["route"]
        if not Path(f"config/keywords/{keyword}.json").exists():
            notes.append(f"keyword={keyword}: config/keywords/{keyword}.json が無いため実行しない")
            continue
        if (Path(survey_dir) / keyword / route).exists():
            notes.append(f"keyword={keyword} route={route}: 結果が既にあるため実行しない(上書き防止。新しい route 名にすること)")
            continue
        targets.append({"prefecture": t.get("prefecture", ""), "keyword": keyword, "route": route, "shards": str(t.get("shards", 1))})
    return targets, notes


def main() -> int:
    targets, notes = plan("config/auto_extract.json", "data/extract", os.environ.get("COMMIT_MESSAGE", ""))
    out = os.environ.get("GITHUB_OUTPUT")
    # 対象が0件でも、matrix が空にならないようダミーを入れる(実行は count の if で止める)
    matrix = {"include": targets or [{"prefecture": "none", "keyword": "none", "route": "none", "shards": "1"}]}
    lines = [f"count={len(targets)}", "matrix=" + json.dumps(matrix, ensure_ascii=False)]
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
    text = "## 自動施設詳細の取り出しの計画\n\n" + ("\n".join(f"- 実行: {t['prefecture'] or '全国'} / keyword `{t['keyword']}` → route `{t['route']}` (shards={t['shards']})" for t in targets) or "- 実行する対象なし") + "\n" + "".join(f"- {n}\n" for n in notes)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
