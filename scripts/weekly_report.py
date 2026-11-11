"""毎週の自動実行(weekly-batch)の結果を集計して、Markdownのレポートにする(D-154)。

  python3 scripts/weekly_report.py --week 2026-11-07 --out data/summary/weekly/latest.md
  python3 scripts/weekly_report.py --list detail     # 施設・イベントの詳細のroute名を空白区切りで出す
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


def routes(cfg: dict, kind: str) -> list[str]:
    prefix = {"facility": cfg["facility_route_prefix"], "event": cfg["event_route_prefix"], "detail": cfg["detail_route_prefix"]}[kind]
    return [prefix + p["slug"] for p in cfg["prefectures"]]


def survey_section(title: str, surveys: list[dict], keyword: str, n_target: int) -> list[str]:
    from localgov_crawler import survey as sv
    rows = sv.survey_rows(surveys)
    surveyed = [r for r in rows if r["outcome"] == "surveyed"]
    found = [r for r in rows if r["found"]]
    capped = [r for r in surveyed if r["stopped"] == "max_pages"]
    capped_all = [r for r in surveyed if r["stopped"] in ("max_pages", "max_requests")]
    outcomes = Counter(r["outcome"] for r in rows if r["outcome"] != "surveyed")
    stopped = Counter(r["stopped"] for r in surveyed)
    pdf_pages = sum(1 for s in surveys for p in s["pages"] if p.get("role") == "pdf")
    ocr_pages = sum(1 for s in surveys for p in s["pages"] if p.get("role") == "pdf" and p.get("ocr"))
    ext_pages = [p for s_ in surveys for p in s_["pages"] if p.get("role") == "external"]
    ext_munis = {s_["municipality"]["code"] for s_ in surveys if s_.get("external_found")}
    retried = sum(1 for s_ in surveys if s_.get("robots_retried"))
    seed_modes = Counter(s_.get("seed_mode", "") for s_ in surveys if s_.get("seed_mode") not in ("normal", "", None))
    lines = [f"### {title}", "", f"- 結果がある自治体: {len(rows)} / 対象 {n_target}", f"- 調査できた: {len(surveyed)} ({(len(surveyed) / n_target if n_target else 0):.1%})",
             f"- ワードがあった自治体: {len(found)}", f"- 上限で止まった: {len(capped_all)} ({(len(capped_all) / len(surveyed) if surveyed else 0):.2%})(うち max_pages {len(capped)}、max_requests {stopped.get('max_requests', 0)})", f"- PDFのページ: {pdf_pages}(うちOCRで読んだ {ocr_pages})"]
    if ext_pages:
        lines.append(f"- 外部サイトのページ: {len(ext_pages)}({len({p['external_host'] for p in ext_pages})}ホスト)、ワードがあった自治体(外部サイトだけで): {len(ext_munis)}")
    if retried:
        lines.append(f"- ロボットファイルをやり直して届いた自治体: {retried}")
    if seed_modes:
        lines.append("- 入口の作り直し: " + "、".join(f"{k} {v}" for k, v in seed_modes.most_common()))
    if outcomes:
        lines.append("- 調査できなかった内訳: " + "、".join(f"{k} {v}" for k, v in outcomes.most_common()))
    return lines + [""]


def compliance_section(surveys: list[dict]) -> list[str]:
    from localgov_crawler import survey as sv
    c = sv.compliance(surveys)
    timed = c["requests"] - c["untimed_requests"]
    lines = ["### 取得ルールの遵守", "", f"- リクエスト {c['requests']}(うち送信時刻を記録 {timed})", f"- 同じホストへの連続リクエストの間隔が1秒未満(0.95秒未満): **{c['interval_violations']}** / {c['timed_pairs']}組"
             + (f"(最小 {c['worst_gap'][0]}秒 自治体{c['worst_gap'][1]} {c['worst_gap'][2]})" if c["worst_gap"] else ""),
             f"- 予約・ログインらしいURLの取得: **{c['reservation_fetched']}**", f"- robots.txt の不許可で飛ばした回数: {c['robots_skipped']}"]
    if c["untimed_requests"]:
        lines.append(f"- 送信時刻なし(ヘッドレスブラウザの取得、または古い形式): {c['untimed_requests']}(計測外)")
    return lines + [""]


def build(cfg: dict, week: str, root: Path = ROOT) -> str:
    from localgov_crawler import events as evm
    from localgov_crawler import extract as ex
    from localgov_crawler import municipalities as mun
    from localgov_crawler import survey as sv
    keyword = cfg["keyword"]
    items = mun.select(mun.load(mun.DEFAULT_MASTER), None, None, None, "municipality")
    n_target = len(items)
    fac = [s for r in routes(cfg, "facility") for s in sv.load_surveys(root / "data/survey", keyword, r)]
    evs = [s for r in routes(cfg, "event") for s in sv.load_surveys(root / "data/survey", keyword, r)]
    lines = [f"# 毎週の自動実行のレポート (keyword: {keyword}, 実行: {week})", "", "## ワード調査", ""]
    lines += survey_section("PDF+OCRつき(施設・PDF)", fac, keyword, n_target)
    lines += survey_section("イベント専用の探索", evs, keyword, n_target)
    both = {s["municipality"]["code"] for s in fac + evs if s["found"]}
    lines += [f"- どちらかでワードがあった自治体(重複なし): {len(both)}", ""]
    lines += compliance_section(fac + evs)
    drows = [row for r in routes(cfg, "detail") for rec in ex.load_extracts(root / "data/extract", keyword, r) for row in ex.detail_rows(rec)]
    erows = [row for r in routes(cfg, "detail") for rec in evm.load_events(root / "data/events", keyword, r) for row in evm.event_rows(rec)]
    lines += ["## 施設の詳細", "", f"- 行数: {len(drows)}({len({r['municipality_code'] for r in drows})}自治体)", f"- 住所あり: {sum(1 for r in drows if r['address'])}、電話あり: {sum(1 for r in drows if r['phone'])}", "",
              "## イベントの詳細", "", f"- 行数: {len(erows)}({len({r['municipality_code'] for r in erows})}自治体)", f"- 開催日あり: {sum(1 for r in erows if r['date_start'])}、会場あり: {sum(1 for r in erows if r['venue'])}、期間内(令和7年度〜): {sum(1 for r in erows if r['period'] == '期間内')}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config/weekly_batch.json"))
    ap.add_argument("--week", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--list", choices=["facility", "event", "detail"])
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.list:
        print(" ".join(routes(cfg, args.list)))
        return 0
    text = build(cfg, args.week)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
