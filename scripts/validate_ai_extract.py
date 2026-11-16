"""Claudeが保存した本文を読んで作った表(JSON)を、本文と突き合わせて検査する(D-165)。

  python3 scripts/validate_ai_extract.py result.json --keyword grandgolf --routes-file config/survey_sets/weekly_facility.json

検査: 根拠(evidence)が本文にそのまま存在するか / pdf_url が空でなく保存した本文にあるか / 自治体コードがあるか /
日付の形式と period の整合 / 個人の連絡先らしきもの(携帯電話・メール)。問題があれば一覧にして、終了コード1を返す。
"""
import argparse
import datetime
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

EVIDENCE_FIELDS = {"facilities": "gg_evidence", "events": "evidence", "organizations": "evidence"}
MOBILE = re.compile(r"(?<!\d)0[789]0[\-ー−‐]?\d{4}[\-ー−‐]?\d{4}(?!\d)")
EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
PERIOD_START = datetime.date(2025, 4, 1)


def norm(t: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", t or ""))


def load_texts(root: Path, keyword: str, routes: list[str], code: str) -> dict[str, str]:
    """自治体コードの保存した本文(PDFとHTMLページ)を、URL → 本文(正規化済み)で返す。"""
    from localgov_crawler import survey as sv
    out: dict[str, str] = {}
    for route in routes:
        for r in sv.load_pdf_texts(root, keyword, route):
            if r["municipality"]["code"] == code:
                for p in r["pdfs"]:
                    out.setdefault(p["url"], norm(p["text"]))
        for r in sv.load_page_texts(root, keyword, route):
            if r["municipality"]["code"] == code:
                for p in r["pages"]:
                    out.setdefault(p["url"], norm(p["text"]))
    return out


def validate(doc: dict, texts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if not doc.get("municipality_code"):
        problems.append("municipality_code が空(1回の入力は1自治体にする)")
    for d in doc.get("documents", []):
        if not d.get("pdf_url"):
            problems.append(f"documents: pdf_url が空: {d.get('title', '')[:30]}")
        elif d["pdf_url"] not in texts:
            problems.append(f"documents: 保存した本文に無いURL: {d['pdf_url'][-60:]}")
    for kind, field in EVIDENCE_FIELDS.items():
        for i, row in enumerate(doc.get(kind, [])):
            label = f"{kind}[{i}] {row.get('facility_name') or row.get('event_name') or row.get('org_name') or ''}"[:50]
            url = row.get("pdf_url", "")
            if not url:
                problems.append(f"{label}: pdf_url が空(どの資料の行か分からない)")
            elif url not in texts:
                problems.append(f"{label}: pdf_url が保存した本文に無い: {url[-60:]}")
            ev = row.get(field, "")
            if not ev:
                problems.append(f"{label}: 根拠({field})が空")
            elif url in texts and norm(ev) not in texts[url]:
                problems.append(f"{label}: 根拠が本文にそのままは無い(要約・言い換え・別の資料の可能性): {ev[:40]}")
            for col in ("phone", "inquiry_phone", "contact_phone", "note"):
                v = str(row.get(col, ""))
                if MOBILE.search(v):
                    problems.append(f"{label}: {col} に携帯電話番号(個人の連絡先の可能性。省略する)")
                if EMAIL.search(v):
                    problems.append(f"{label}: {col} にメールアドレス(個人の可能性。省略する)")
            if kind == "events":
                ds, de = row.get("date_start", ""), row.get("date_end", "")
                for name, v in (("date_start", ds), ("date_end", de)):
                    if v:
                        try:
                            datetime.date.fromisoformat(v)
                        except ValueError:
                            problems.append(f"{label}: {name} が YYYY-MM-DD でない: {v}")
                try:
                    base = datetime.date.fromisoformat(ds or de) if (ds or de) else None
                except ValueError:
                    base = None
                want = "日付不明" if base is None else ("期間内" if base >= PERIOD_START else "期間外")
                if row.get("period") and row["period"] != want:
                    problems.append(f"{label}: period が日付と合わない(日付からは {want}、記載は {row['period']})")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--routes-file")
    ap.add_argument("--routes", nargs="+")
    ap.add_argument("--surveys", default=str(ROOT / "data/survey"))
    a = ap.parse_args()
    routes = json.loads(Path(a.routes_file).read_text(encoding="utf-8"))["routes"] if a.routes_file else a.routes
    doc = json.loads(Path(a.result).read_text(encoding="utf-8"))
    texts = load_texts(Path(a.surveys), a.keyword, routes, doc.get("municipality_code", ""))
    problems = validate(doc, texts)
    n = sum(len(doc.get(k, [])) for k in EVIDENCE_FIELDS)
    print(f"行 {n}件(施設{len(doc.get('facilities', []))}・イベント{len(doc.get('events', []))}・団体{len(doc.get('organizations', []))})、問題 {len(problems)}件")
    for p in problems:
        print("-", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
