"""config/weekly_batch.json から、毎週の自動実行の対象(県ごと)を決めて、GitHub Actionsの出力に書く(D-154)。"""
import datetime
import json
import os
import sys
from pathlib import Path

JST = datetime.timezone(datetime.timedelta(hours=9))


def plan(config_path: str, only_prefecture: str = "") -> tuple[list[dict], list[str]]:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if not cfg.get("enabled", False):
        return [], ["config/weekly_batch.json の enabled が false のため、実行しない"]
    keyword = cfg["keyword"]
    if not Path(f"config/keywords/{keyword}.json").exists():
        return [], [f"config/keywords/{keyword}.json が無いため、実行しない"]
    targets, notes = [], []
    for p in cfg["prefectures"]:
        if only_prefecture and only_prefecture not in (p["name"], p["slug"]):
            continue
        targets.append({
            "prefecture": p["name"], "slug": p["slug"], "shards": str(p.get("shards", 1)), "keyword": keyword, "from_route": cfg.get("from_route", "redecide_v12_1"),
            "facility_route": cfg["facility_route_prefix"] + p["slug"], "event_route": cfg["event_route_prefix"] + p["slug"], "detail_route": cfg["detail_route_prefix"] + p["slug"],
            "facility_max_pages": str(cfg.get("facility_max_pages", 200)), "facility_max_pdfs": str(cfg.get("facility_max_pdfs", 20)), "follow_external": "1" if cfg.get("follow_external") else "", "event_max_pages": str(cfg.get("event_max_pages", 300)),
        })
    if only_prefecture and not targets:
        notes.append(f"県 {only_prefecture} が config/weekly_batch.json に無い")
    return targets, notes


def main() -> int:
    targets, notes = plan("config/weekly_batch.json", os.environ.get("PREFECTURE", ""))
    week = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    dummy = {"prefecture": "none", "slug": "none", "shards": "1", "keyword": "none", "from_route": "none", "facility_route": "none", "event_route": "none", "detail_route": "none", "facility_max_pages": "1", "facility_max_pdfs": "1", "follow_external": "", "event_max_pages": "1"}
    lines = [f"count={len(targets)}", f"week={week}", "matrix=" + json.dumps({"include": targets or [dummy]}, ensure_ascii=False)]
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
    text = f"## 毎週の自動実行の計画({week}、日本時間)\n\n" + (f"- 対象: {len(targets)}県(シャード合計 {sum(int(t['shards']) for t in targets)})\n" if targets else "- 実行する対象なし\n") + "".join(f"- {n}\n" for n in notes)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
