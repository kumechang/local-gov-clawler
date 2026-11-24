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
    # 全部まとめた1枚(種類の列つき)と、読んだPDFの一覧(関係あり・なしと理由)
    allrows = []
    for d in docs:
        base = {"自治体コード": d["municipality_code"], "自治体名": d["municipality_name"]}
        for r in d.get("facilities", []):
            allrows.append({**base, "種類": "施設", "名称": r.get("facility_name", ""), "場所": r.get("address", ""), "日付": "", "期間": "", "内容": r.get("usage_note", ""),
                            "連絡先": " ".join(x for x in (r.get("inquiry_dept", ""), r.get("inquiry_phone", "") or r.get("phone", "")) if x), "根拠": r.get("gg_evidence", ""), "資料のURL(PDFまたはHTMLページ)": r.get("pdf_url", ""), "信頼度": r.get("confidence", ""), "備考": r.get("note", "")})
        for r in d.get("events", []):
            allrows.append({**base, "種類": "イベント", "名称": r.get("event_name", ""), "場所": r.get("venue", ""), "日付": r.get("date_text", "") or r.get("date_start", ""), "期間": r.get("period", ""),
                            "内容": " / ".join(x for x in (r.get("event_kind", ""), ("主催: " + r["organizer"]) if r.get("organizer") else "", ("対象: " + r["target"]) if r.get("target") else "", ("参加費: " + r["fee"]) if r.get("fee") else "") if x),
                            "連絡先": " ".join(x for x in (r.get("contact_dept", ""), r.get("contact_phone", "")) if x), "根拠": r.get("evidence", ""), "資料のURL(PDFまたはHTMLページ)": r.get("pdf_url", ""), "信頼度": r.get("confidence", ""), "備考": r.get("note", "")})
        for r in d.get("organizations", []):
            allrows.append({**base, "種類": "団体", "名称": r.get("org_name", ""), "場所": r.get("activity_place", ""), "日付": "", "期間": "", "内容": " / ".join(x for x in (r.get("org_kind", ""), r.get("activity_schedule", "")) if x),
                            "連絡先": " ".join(x for x in (r.get("contact_dept", ""), r.get("contact_phone", "")) if x), "根拠": r.get("evidence", ""), "資料のURL(PDFまたはHTMLページ)": r.get("pdf_url", ""), "信頼度": r.get("confidence", ""), "備考": r.get("note", "")})
    cols_all = ["種類", "自治体コード", "自治体名", "名称", "場所", "日付", "期間", "内容", "連絡先", "根拠", "資料のURL(PDFまたはHTMLページ)", "信頼度", "備考"]
    with open(out / f"{keyword}_ai_all.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_all)
        w.writeheader()
        w.writerows(allrows)
    docrows = [{"自治体コード": d["municipality_code"], "自治体名": d["municipality_name"], "資料のURL(PDFまたはHTMLページ)": x.get("pdf_url", ""), "題名": x.get("title", ""), "資料の種類": x.get("doc_kind", ""), "関係あり": "○" if x.get("relevant") else "×", "スキップの理由": x.get("skip_reason", "")} for d in docs for x in d.get("documents", [])]
    with open(out / f"{keyword}_ai_documents.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["自治体コード", "自治体名", "資料のURL(PDFまたはHTMLページ)", "題名", "資料の種類", "関係あり", "スキップの理由"])
        w.writeheader()
        w.writerows(docrows)
    counts["all"] = len(allrows)
    counts["documents"] = len(docrows)
    counts["municipalities"] = len(docs)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--src", default="")
    ap.add_argument("--out", default=str(ROOT / "data/export/ai"))
    a = ap.parse_args()
    c = build(Path(a.src) if a.src else ROOT / "data/extract_ai" / a.keyword, Path(a.out), a.keyword)
    print(f"全部まとめた行 {c['all']} / 読んだPDF {c['documents']} / 自治体 {c['municipalities']} / 施設 {c['facilities']} / イベント {c['events']} / 団体 {c['organizations']} / 要確認 {c['unsure']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
