"""Claudeが保存した本文を読んで作った表(data/extract_ai/<keyword>/*.json)を、種類ごとのCSVにまとめる(D-168)。

  python3 scripts/build_ai_extract_csv.py --keyword grandgolf --out data/export/ai
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
COLUMNS = {
    "facilities": ["facility_name", "address", "phone", "inquiry_dept", "inquiry_phone", "usage_note", "gg_evidence", "pdf_url", "confidence", "note"],
    "events": ["event_name", "event_kind", "date_text", "date_start", "date_end", "fiscal_year", "period", "venue", "organizer", "target", "fee", "entry", "deadline", "contact_dept", "contact_phone", "evidence", "pdf_url", "confidence", "note"],
    "organizations": ["org_name", "org_kind", "activity_place", "activity_schedule", "contact_dept", "contact_phone", "evidence", "pdf_url", "confidence", "note"],
}


def build(src: Path, out: Path, keyword: str) -> dict[str, int]:
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(src.glob("*.json"))]
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for kind, cols in COLUMNS.items():
        rows = [{"municipality_code": d["municipality_code"], "municipality_name": d["municipality_name"], **{c: r.get(c, "") for c in cols}} for d in docs for r in d.get(kind, [])]
        with open(out / f"{keyword}_ai_{kind}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["municipality_code", "municipality_name"] + cols)
            w.writeheader()
            w.writerows(rows)
        counts[kind] = len(rows)
    uns = [{"municipality_code": d["municipality_code"], "municipality_name": d["municipality_name"], "pdf_url": u.get("pdf_url", ""), "note": u.get("note", "")} for d in docs for u in d.get("unsure", [])]
    with open(out / f"{keyword}_ai_unsure.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["municipality_code", "municipality_name", "pdf_url", "note"])
        w.writeheader()
        w.writerows(uns)
    counts["unsure"] = len(uns)
    counts["municipalities"] = len(docs)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--src", default="")
    ap.add_argument("--out", default=str(ROOT / "data/export/ai"))
    a = ap.parse_args()
    c = build(Path(a.src) if a.src else ROOT / "data/extract_ai" / a.keyword, Path(a.out), a.keyword)
    print(f"自治体 {c['municipalities']} / 施設 {c['facilities']} / イベント {c['events']} / 団体 {c['organizations']} / 要確認 {c['unsure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
