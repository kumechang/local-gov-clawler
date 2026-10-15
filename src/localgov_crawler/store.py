"""結果の保存(1自治体1JSON。差分が読めるようリポジトリにはJSONを正とする)、SQLite生成、集計、評価。"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag

from .municipalities import Municipality


def result_path(root: Path, route: str, m_prefecture_code: str, code: str) -> Path:
    return Path(root) / route / m_prefecture_code / f"{code}.json"


def compact_result(result: dict) -> dict:
    """全国実行用の軽量形式(D-062)。サイト内リンク一覧(1件あたり約33KBで、容量の大半)を捨て、件数だけ残す。
    ハブ候補・判定・リクエスト記録・サイトプロファイルはそのまま残す。"""
    out = dict(result)
    out["nav_link_count"] = len(result.get("nav_links", []))
    out["nav_links"] = []
    out["run"] = {**result["run"], "compact": True}
    return out


def write_result(root: Path, result: dict, prefecture_code: str, compact: bool = False) -> Path:
    path = result_path(root, result["run"]["route"], prefecture_code, result["municipality"]["code"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(compact_result(result), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    else:
        text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
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
    """比較用のURL正規化: フラグメント・末尾スラッシュ・大文字小文字・スキーム(http/https)・先頭の www. の違いを無視する。"""
    u = urldefrag(u.strip())[0].rstrip("/").lower()
    u = re.sub(r"^https?://", "", u)
    return re.sub(r"^www\.", "", u)


def evaluate(results: list[dict], truth_csv: Path) -> dict:
    """正解データ(municipality_code,hub_url)に対する採点。

    - reach: 正解URLがハブ候補の上位5件に入った(AI判定や手動確認に渡せば拾える水準)
    - selected_correct: プログラムが確定(hub_selected)したURLが正解と一致した(そのまま使える水準)
    hub_urlが空の行(サイトに一覧ページが無い)は到達・正解の母数に含めないが、プログラムが何かを確定していたら
    誤りとして数える(none_selected、selected_precision_all)。
    許容URLは alt_urls 列(空白または | 区切り)に書ける。どれか1つに一致すれば正解。
    """
    by_code = {r["municipality"]["code"]: r for r in results}
    rows = list(csv.DictReader(open(truth_csv, encoding="utf-8-sig")))
    all_rows = [r for r in rows if r.get("municipality_code")]
    none_codes = [r["municipality_code"].zfill(5) for r in all_rows if not (r.get("hub_url") or "").strip()]
    rows = [r for r in all_rows if (r.get("hub_url") or "").strip()]
    detail = []
    for row in rows:
        code = row["municipality_code"].zfill(5)
        r = by_code.get(code)
        truths = {_norm_url(u) for u in re.split(r"[\s|]+", f"{row['hub_url']} {row.get('alt_urls') or ''}") if u}
        reached, rank, selected_url = False, None, None
        if r:
            for ge in r["genre_entrypoints"]:
                urls = [_norm_url(c["url"]) for c in ge["candidates"]]
                hits = [i for i, u in enumerate(urls) if u in truths]
                if hits:
                    reached, rank = True, hits[0] + 1
                if ge.get("selected"):
                    selected_url = ge["selected"]["url"]
        detail.append({
            "code": code, "reached": reached, "rank": rank, "outcome": r["outcome"] if r else "missing",
            "selected_url": selected_url,
            "selected_correct": (_norm_url(selected_url) in truths) if selected_url else None,
        })
    n = len(detail)
    reached = sum(d["reached"] for d in detail)
    selected = [d for d in detail if d["selected_url"]]
    correct = sum(1 for d in selected if d["selected_correct"])
    # 正解が「なし」の自治体で、プログラムが何かを確定していたら誤り
    none_selected = sum(1 for c in none_codes if c in by_code and any(ge.get("selected") for ge in by_code[c]["genre_entrypoints"]))
    all_selected = len(selected) + none_selected
    return {
        "none_rows": len(none_codes),
        "none_selected": none_selected,
        "selected_precision_all": round(correct / all_selected, 3) if all_selected else None,
        "truth_count": n,
        "reached": reached,
        "reach_rate": round(reached / n, 3) if n else None,
        "selected": len(selected),
        "selected_correct": correct,
        "selected_precision": round(correct / len(selected), 3) if selected else None,
        "selected_correct_rate": round(correct / n, 3) if n else None,
        "detail": detail,
    }
