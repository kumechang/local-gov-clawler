"""毎週の自動実行の、前週との差分(D-158)。前週のCSVと今週のCSVを比べて、新しく見つかったもの・無くなったものを出す。

  python3 scripts/weekly_diff.py --prev prev --new data/export/weekly --out data/export/weekly/diff --md data/summary/weekly/diff.md
"""
import argparse
import csv
import sys
from pathlib import Path

# (ファイル, 表示名, 同じものとみなす列)
TARGETS = [
    ("grandgolf_places.csv", "ワードのあったページ(場所)", ("municipality_code", "page_url")),
    ("grandgolf_events.csv", "ワードのあったページ(イベント)", ("municipality_code", "page_url")),
    ("grandgolf_others.csv", "ワードのあったページ(団体・その他)", ("municipality_code", "page_url")),
    ("event_focus/grandgolf_places.csv", "イベント探索:ワードのあったページ(場所)", ("municipality_code", "page_url")),
    ("event_focus/grandgolf_events.csv", "イベント探索:ワードのあったページ(イベント)", ("municipality_code", "page_url")),
    ("event_focus/grandgolf_others.csv", "イベント探索:ワードのあったページ(団体・その他)", ("municipality_code", "page_url")),
    ("grandgolf_places_detail.csv", "施設の詳細", ("municipality_code", "facility_name", "page_url")),
    ("grandgolf_events_detail.csv", "イベントの詳細", ("municipality_code", "event_name", "date_start")),
    ("grandgolf_pdfs.csv", "ワードのあったPDF", ("municipality_code", "pdf_url")),
]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def diff(prev: list[dict], new: list[dict], key: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    k = lambda r: tuple(r.get(c, "") for c in key)
    pk, nk = {k(r) for r in prev}, {k(r) for r in new}
    seen: set = set()
    added = [r for r in new if k(r) not in pk and not (k(r) in seen or seen.add(k(r)))]
    seen = set()
    removed = [r for r in prev if k(r) not in nk and not (k(r) in seen or seen.add(k(r)))]
    return added, removed


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys()) if rows else ["municipality_code"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def build(prev_dir: Path, new_dir: Path, out_dir: Path) -> str:
    lines = ["## 前週との差分", ""]
    if not prev_dir.exists() or not any(prev_dir.glob("*.csv")):
        return "\n".join(lines + ["- 前週のCSVが無いため、差分なし(今週が最初)", ""])
    lines += ["| 項目 | 前週 | 今週 | 新しい | 無くなった |", "|---|---|---|---|---|"]
    towns_prev: set[str] = set()
    towns_new: set[str] = set()
    for fname, label, key in TARGETS:
        prev, new = read(prev_dir / fname), read(new_dir / fname)
        added, removed = diff(prev, new, key)
        stem = fname.removesuffix(".csv").replace("/", "_")
        write_csv(out_dir / f"{stem}_new.csv", added)
        write_csv(out_dir / f"{stem}_removed.csv", removed)
        lines.append(f"| {label} | {len(prev)} | {len(new)} | {len(added)} | {len(removed)} |")
        if "_detail" not in fname and "pdfs" not in fname:
            towns_prev |= {r["municipality_code"] for r in prev}
            towns_new |= {r["municipality_code"] for r in new}
    gained, lost = sorted(towns_new - towns_prev), sorted(towns_prev - towns_new)
    names = {r["municipality_code"]: f"{r['prefecture']}{r['municipality_name']}" for fname, _, _ in TARGETS[:6] for r in read(new_dir / fname) + read(prev_dir / fname)}
    lines += ["", f"- ワードのあった自治体: 前週 {len(towns_prev)} → 今週 {len(towns_new)}(新しく {len(gained)}、無くなった {len(lost)})"]
    if gained:
        lines.append("  - 新しく: " + "、".join(names.get(c, c) for c in gained[:30]) + (" ほか" if len(gained) > 30 else ""))
    if lost:
        lines.append("  - 無くなった: " + "、".join(names.get(c, c) for c in lost[:30]) + (" ほか" if len(lost) > 30 else ""))
    lines += ["", f"新しい行・無くなった行のCSVは `{out_dir}/` にある。", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--md", default="")
    a = ap.parse_args()
    text = build(Path(a.prev), Path(a.new), Path(a.out))
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
