"""config/auto_crawl.json から、自動クロールの対象(結果が未作成のroute)を決めて、GitHub Actionsの出力に書く。"""
import json
import os
import sys
from pathlib import Path


def plan(config_path: str, results_dir: str, commit_message: str) -> tuple[list[dict], list[str]]:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    notes: list[str] = []
    if not cfg.get("enabled", False):
        return [], ["config/auto_crawl.json の enabled が false のため、実行しない"]
    if "[skip crawl]" in commit_message:
        return [], ["コミットメッセージに [skip crawl] があるため、実行しない"]
    targets = []
    for t in cfg.get("targets", []):
        route = t["route"]
        if (Path(results_dir) / route).exists():
            notes.append(f"route={route}: 結果が既にあるため実行しない(上書き防止。新しい route 名にすること)")
            continue
        # scope(空=すべて / municipality=区を除く)と compact(軽量形式)は省略可。matrixの全要素に同じキーが要る
        targets.append({"prefecture": t["prefecture"], "route": route, "scope": t.get("scope", ""), "compact": bool(t.get("compact", False))})
    return targets, notes


def main() -> int:
    targets, notes = plan("config/auto_crawl.json", "data/results", os.environ.get("COMMIT_MESSAGE", ""))
    out = os.environ.get("GITHUB_OUTPUT")
    # 対象が0件でも、matrix が空にならないようダミーを入れる(実行は count の if で止める)
    matrix = {"include": targets or [{"prefecture": "none", "route": "none", "scope": "", "compact": False}]}
    lines = [f"count={len(targets)}", "matrix=" + json.dumps(matrix, ensure_ascii=False)]
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "## 自動クロールの計画\n\n" + ("\n".join(f"- 実行: {t['prefecture']} → route `{t['route']}`" + (f" (scope={t['scope']})" if t["scope"] else "") + (" [compact]" if t["compact"] else "") for t in targets) or "- 実行する対象なし") + "\n" + "".join(f"- {n}\n" for n in notes)
    if summary:
        Path(summary).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
