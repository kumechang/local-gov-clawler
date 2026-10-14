"""結果の保存(1自治体1JSON。差分が読めるようリポジトリにはJSONを正とする)、SQLite生成、集計、評価。"""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag

from .municipalities import Municipality


def result_path(root: Path, route: str, m_prefecture_code: str, code: str) -> Path:
    return Path(root) / route / m_prefecture_code / f"{code}.json"


def write_result(root: Path, result: dict, prefecture_code: str) -> Path:
    path = result_path(root, result["run"]["route"], prefecture_code, result["municipality"]["code"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_results(root: Path, route: str) -> list[dict]:
    base = Path(root) / route
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("*/*.json"))]


def build_db(root: Path, route: str, masters: list[Municipality], db_path: Path) -> None:
    results = {r["municipality"]["code"]: r for r in load_results(root, route)}
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE municipalities(code TEXT PRIMARY KEY, name TEXT, full_name TEXT, prefecture TEXT, kind TEXT, scope TEXT,
            official_url TEXT, status TEXT, last_fetched_at TEXT);
        CREATE TABLE site_profiles(municipality_code TEXT PRIMARY KEY, route TEXT, final_url TEXT, top_status INTEGER, failure_class TEXT,
            robots_available INTEGER, crawl_delay REAL, sitemap_found INTEGER, sitemap_url TEXT, sitemap_url_count INTEGER,
            cms_family TEXT, cms_confidence TEXT, needs_headless INTEGER, fetch_method TEXT, used_proxy INTEGER, provenance TEXT);
        CREATE TABLE genre_entrypoints(municipality_code TEXT, genre TEXT, url TEXT, score INTEGER, decision TEXT, provenance TEXT, rank INTEGER);
        CREATE TABLE nav_links(municipality_code TEXT, text TEXT, url TEXT, region TEXT);
        """
    )
    for m in masters:
        r = results.get(m.code)
        con.execute("INSERT INTO municipalities VALUES(?,?,?,?,?,?,?,?,?)", (m.code, m.name, m.full_name, m.prefecture_name, m.kind, m.scope, m.url,
                    r["outcome"] if r else "pending", r["run"]["finished_at"] if r else ""))
        if not r:
            continue
        p = r["site_profile"]
        sm, cms, rd, top, rb = p.get("sitemap", {}), p.get("cms", {}), p.get("rendering", {}), p.get("top", {}), p.get("robots", {})
        con.execute("INSERT INTO site_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            m.code, route, top.get("final_url"), top.get("status"), r["failure_class"], int(bool(rb.get("available"))), rb.get("crawl_delay"),
            int(bool(sm.get("found"))), sm.get("url"), sm.get("url_count"), cms.get("family"), cms.get("confidence"),
            int(bool(rd.get("needs_headless"))), p.get("fetch_method"), int(bool(p.get("used_proxy"))), "auto"))
        for ge in r["genre_entrypoints"]:
            for i, c in enumerate(ge["candidates"]):
                con.execute("INSERT INTO genre_entrypoints VALUES(?,?,?,?,?,?,?)", (m.code, ge["genre"], c["url"], c["score"], ge["decision"], ge["provenance"], i + 1))
        for l in r["nav_links"]:
            con.execute("INSERT INTO nav_links VALUES(?,?,?,?)", (m.code, l["text"], l["url"], l["region"]))
    con.commit()
    con.close()


def summarize(results: list[dict]) -> dict:
    n = len(results)
    if not n:
        return {"total": 0}
    outcomes = Counter(r["outcome"] for r in results)
    fails = Counter(r["failure_class"] for r in results if r["failure_class"])
    profiles = [r["site_profile"] for r in results if r["site_profile"].get("top", {}).get("status")]
    fetched = [r for r in results if r["site_profile"].get("top") and not r["failure_class"]]
    cms = Counter(r["site_profile"].get("cms", {}).get("family", "n/a") for r in fetched)
    undecided = outcomes["hub_multiple"] + outcomes["hub_not_found"]
    return {
        "total": n,
        "route": results[0]["run"]["route"],
        "outcomes": dict(outcomes),
        "failure_classes": dict(fails),
        "fetch_failure_rate": round(sum(1 for r in results if r["outcome"] == "fetch_failed") / n, 3),
        "hub_selected_rate": round(outcomes["hub_selected"] / n, 3),
        "program_only_resolved": outcomes["hub_selected"],
        "ai_needed": sum(1 for r in results if r["ai_needed"]),
        "undecided_hub": undecided,
        "needs_headless": sum(1 for r in fetched if r["site_profile"].get("rendering", {}).get("needs_headless")),
        "sitemap_found": sum(1 for r in fetched if r["site_profile"].get("sitemap", {}).get("found")),
        "robots_available": sum(1 for r in fetched if r["site_profile"].get("robots", {}).get("available")),
        "cms_families": dict(cms.most_common()),
        "avg_requests": round(sum(r["run"].get("request_count", 0) for r in results) / n, 1),
        "avg_elapsed_ms": int(sum(r["run"].get("elapsed_ms", 0) for r in results) / n),
        "municipalities_failed": sorted(r["municipality"]["code"] for r in results if r["outcome"] == "fetch_failed"),
    }


def summary_markdown(s: dict) -> str:
    if not s.get("total"):
        return "結果なし\n"
    lines = [f"# 構造解析サマリ (route: {s['route']})", "", f"- 対象: {s['total']}自治体", f"- 取得失敗率: {s['fetch_failure_rate']:.1%}",
             f"- ハブ候補をプログラムのみで確定: {s['program_only_resolved']} ({s['hub_selected_rate']:.1%})",
             f"- AI判定に回る(取れたが判断できない): {s['ai_needed']}", f"- JS描画フォールバック要: {s['needs_headless']}",
             f"- サイトマップ検出: {s['sitemap_found']} / robots.txt取得: {s['robots_available']}",
             f"- 平均リクエスト数: {s['avg_requests']} / 平均所要時間: {s['avg_elapsed_ms']}ms", "", "## outcome別", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(s["outcomes"].items())]
    lines += ["", "## 失敗原因", ""] + ([f"- {k}: {v}" for k, v in sorted(s["failure_classes"].items())] or ["- なし"])
    lines += ["", "## CMS推定", ""] + [f"- {k}: {v}" for k, v in s["cms_families"].items()]
    return "\n".join(lines) + "\n"


def _norm_url(u: str) -> str:
    return urldefrag(u.strip())[0].rstrip("/").lower()


def evaluate(results: list[dict], truth_csv: Path) -> dict:
    """正解データ(municipality_code,hub_url)に対し、候補(上位5件+選択+その配下リンク)に到達できたかを数える。"""
    by_code = {r["municipality"]["code"]: r for r in results}
    rows = list(csv.DictReader(open(truth_csv, encoding="utf-8-sig")))
    rows = [r for r in rows if r.get("municipality_code") and r.get("hub_url")]
    detail = []
    for row in rows:
        code = row["municipality_code"].zfill(5)
        r = by_code.get(code)
        truth = _norm_url(row["hub_url"])
        reached, rank = False, None
        if r:
            for ge in r["genre_entrypoints"]:
                urls = [_norm_url(c["url"]) for c in ge["candidates"]]
                if truth in urls:
                    reached, rank = True, urls.index(truth) + 1
        detail.append({"code": code, "reached": reached, "rank": rank, "outcome": r["outcome"] if r else "missing"})
    n = len(detail)
    return {"truth_count": n, "reached": sum(d["reached"] for d in detail), "reach_rate": round(sum(d["reached"] for d in detail) / n, 3) if n else None, "detail": detail}
