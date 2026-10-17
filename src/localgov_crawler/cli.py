"""コマンドライン。run / merge-db / summarize / evaluate / compare / list / review-list。"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import municipalities as mun
from . import store
from .fetcher import DEFAULT_CONTACT, Fetcher, build_user_agent
from .pipeline import Config, analyze


def _shard(arg: str | None):
    if not arg:
        return None
    i, n = arg.split("/")
    return int(i), int(n)


def _select(args):
    items = mun.load(args.master)
    return items, mun.select(items, args.prefecture, args.code, _shard(args.shard), getattr(args, "scope", None) or None)


def cmd_list(args) -> int:
    _, sel = _select(args)
    for m in sel:
        print(m.code, m.name, m.url)
    print(f"{len(sel)} municipalities", file=sys.stderr)
    return 0


def cmd_run(args) -> int:
    _, sel = _select(args)
    proxy = os.environ.get("CRAWL_PROXY_URL") if args.use_proxy else None
    if args.use_proxy and not proxy:
        print("--use-proxy が指定されましたが CRAWL_PROXY_URL が未設定です", file=sys.stderr)
        return 2
    contact = os.environ.get("CRAWLER_CONTACT", DEFAULT_CONTACT)
    cfg = Config(route=args.route, save_html_dir=Path(args.save_html) if args.save_html else None)
    out = Path(args.out)

    # 並列化はホスト単位。同じホスト(政令市の区は親市と同じホスト)の自治体は1つのワーカーが順番に処理し、
    # Fetcher(最小間隔の管理)を共有するので、1ホストへのリクエストは常に1秒に1回以下になる(D-096)
    lock = threading.Lock()

    def work(group):
        f = Fetcher(user_agent=build_user_agent(contact), proxy=proxy, min_interval=args.interval)
        try:
            for m in group:
                res = analyze(m, f, cfg)
                store.write_result(out, res, m.prefecture_code, compact=args.compact)
                with lock:
                    counter[0] += 1
                    print(f"[{counter[0]}/{len(sel)}] {m.code} {m.name}: {res['outcome']} {res['failure_class']}".strip(), flush=True)
        finally:
            f.close()

    counter = [0]
    groups = group_by_host(sel)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(work, g) for g in groups]
        for fut in as_completed(futures):
            fut.result()
    return 0


def group_by_host(sel):
    """同じホストの自治体をまとめる(順序は保つ)。ホストが空の自治体は単独のグループ。"""
    groups: dict[str, list] = {}
    for m in sel:
        groups.setdefault(m.host or f"_nohost_{m.code}", []).append(m)
    return list(groups.values())


def cmd_merge_db(args) -> int:
    items = mun.load(args.master)
    if args.prefecture:
        items = mun.select(items, args.prefecture)
    store.build_db(Path(args.results), args.route, items, Path(args.db))
    print(f"wrote {args.db}")
    return 0


def cmd_summarize(args) -> int:
    s = store.summarize(store.load_results(Path(args.results), args.route))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.route}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / f"{args.route}.md").write_text(store.summary_markdown(s), encoding="utf-8")
    print(store.summary_markdown(s))
    return 0


def cmd_evaluate(args) -> int:
    ev = store.evaluate(store.load_results(Path(args.results), args.route), Path(args.truth))
    print(json.dumps(ev, ensure_ascii=False, indent=1))
    return 0


def cmd_compare(args) -> int:
    print("route\ttotal\tfetch_failure_rate\thub_selected_rate\tneeds_headless")
    for route in args.routes:
        s = store.summarize(store.load_results(Path(args.results), route))
        if s.get("total"):
            print(f"{route}\t{s['total']}\t{s['fetch_failure_rate']:.1%}\t{s['hub_selected_rate']:.1%}\t{s['needs_headless']}")
    return 0


def cmd_review_list(args) -> int:
    """確定できなかった自治体を、都道府県別のCSV(手動確認用、候補つき)に書き出す。"""
    items = {m.code: m for m in mun.load(args.master)}
    results = []
    for route in args.routes:
        results += store.load_results(Path(args.results), route)
    by_pref: dict[str, list[dict]] = {}
    for r in results:
        by_pref.setdefault(items[r["municipality"]["code"]].prefecture_code, []).append(r)
    total = 0
    for pc, rs in sorted(by_pref.items()):
        rows = store.review_rows(rs)
        if rows:
            name = items[rows[0]["municipality_code"]].prefecture_name
            store.write_review_csv(Path(args.out) / f"{pc}_{name}.csv", rows)
            total += len(rows)
    print(f"{total} municipalities to review → {args.out}")
    return 0


def cmd_ward_report(args) -> int:
    """政令市の区の結果を親市と比べ、CSVと概要に書き出す(D-096)。"""
    items = {m.code: m for m in mun.load(args.master)}
    parent_of = {c: m.parent_code for c, m in items.items() if m.scope == "designated_city_ward"}
    wards, parents = [], {}
    for route in args.ward_routes:
        wards += store.load_results(Path(args.results), route)
    for route in args.parent_routes:
        for r in store.load_results(Path(args.results), route):
            parents[r["municipality"]["code"]] = r
    rows = store.ward_rows(wards, parents, parent_of)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "wards.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    rel = Counter(r["relation"] for r in rows)
    oc = Counter(r["ward_outcome"] for r in rows)
    text = [f"# 政令市の区の結果(D-096)", "", f"- 区: {len(rows)}件", f"- 関係: " + "、".join(f"{k} {v}" for k, v in sorted(rel.items())),
            f"- 区の結果: " + "、".join(f"{k} {v}" for k, v in sorted(oc.items())),
            f"- 区または親市のハブが分かる(`effective_hub_url`あり): {sum(1 for r in rows if r['effective_hub_url'])}件", ""]
    (out / "wards.md").write_text("\n".join(text), encoding="utf-8")
    print("\n".join(text))
    return 0


def cmd_redecide(args) -> int:
    """保存済みの結果にハブの判定ルールをやり直して、新しいrouteに書く(自治体サイトには接続しない、D-104)。"""
    from .redecide import redecide
    n = changed = 0
    for route in args.from_routes:
        for r in store.load_results(Path(args.results), route):
            new = redecide(r, args.route, args.rules)
            store.write_result(Path(args.out), new, r["municipality"]["code"][:2], compact=args.compact)
            n += 1
            changed += new["outcome"] != r["outcome"]
    print(f"{n} results → {args.out}/{args.route} ({changed} outcomes changed)")
    return 0


def cmd_survey(args) -> int:
    """保存済みのハブ判定の結果を入口に、ワードがあるページを調べる(D-107)。ホスト単位の処理は run と同じ(1ホスト1リクエスト/秒以下)。"""
    from . import survey as sv
    _, sel = _select(args)
    spec = sv.KeywordSpec.load(args.keywords)
    stored = {r["municipality"]["code"]: r for r in store.load_results(Path(args.results), args.from_route)}
    proxy = os.environ.get("CRAWL_PROXY_URL") if args.use_proxy else None
    contact = os.environ.get("CRAWLER_CONTACT", DEFAULT_CONTACT)
    cfg = sv.SurveyConfig(route=args.route, max_pages=args.max_pages, seed_depth=args.depth)
    out = Path(args.out)
    lock = threading.Lock()
    counter = [0]

    def work(group):
        f = Fetcher(user_agent=build_user_agent(contact), proxy=proxy, min_interval=args.interval)
        hl = None
        try:
            for m in group:
                r = stored.get(m.code)
                fetcher, before = f, (0, 0)
                # JS描画のサイトは、ヘッドレスブラウザで取得する(handoff §2のフォールバック。D-117)
                if args.headless and r and r.get("site_profile", {}).get("rendering", {}).get("needs_headless"):
                    from .headless import HeadlessFetcher, HybridFetcher
                    hl = hl or HeadlessFetcher(build_user_agent(contact), min_interval=args.interval)
                    fetcher, before = HybridFetcher(f, hl), (hl.pages, hl.subrequests)
                res = sv.survey_municipality(m, r, fetcher, spec, cfg)
                if fetcher is not f:
                    res["run"]["headless"] = {"pages": hl.pages - before[0], "subrequests": hl.subrequests - before[1]}
                sv.write_survey(out, res, m.prefecture_code)
                with lock:
                    counter[0] += 1
                    print(f"[{counter[0]}/{len(sel)}] {m.code} {m.name}: {res['outcome']} found={res['found']} pages={res.get('pages_fetched', 0)} {res['failure_class']}".strip(), flush=True)
        finally:
            f.close()
            if hl is not None:
                hl.close()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in as_completed([ex.submit(work, g) for g in group_by_host(sel)]):
            fut.result()
    return 0


def cmd_survey_summary(args) -> int:
    from . import survey as sv
    rows = sv.survey_rows(sv.load_surveys(Path(args.surveys), args.keyword, args.route))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"survey_{args.keyword}_{args.route}"
    if rows:
        with open(out / f"{stem}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    text = sv.summary_markdown(rows, args.keyword)
    (out / f"{stem}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="localgov-crawler")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_select(sp):
        sp.add_argument("--master", default=str(mun.DEFAULT_MASTER))
        sp.add_argument("--prefecture", help="都道府県名または2桁コード")
        sp.add_argument("--code", action="append", help="自治体コード(複数指定可)")
        sp.add_argument("--shard", help="i/n 形式(例: 0/4)")
        sp.add_argument("--scope", choices=["municipality", "designated_city_ward"], help="municipality=区を除く / designated_city_ward=政令市の区のみ")

    sp = sub.add_parser("list"); add_select(sp); sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("run"); add_select(sp)
    sp.add_argument("--route", default="local", help="取得経路ラベル(actions_direct / proxy / local)")
    sp.add_argument("--out", default="data/results")
    sp.add_argument("--workers", type=int, default=4)
    sp.add_argument("--interval", type=float, default=1.0, help="同一ホストへの最小リクエスト間隔(秒)")
    sp.add_argument("--compact", action="store_true", help="軽量形式で保存(インデント無しの1行JSON。リンク一覧は残す。全国実行用、D-062/D-065)")
    sp.add_argument("--use-proxy", action="store_true", help="環境変数 CRAWL_PROXY_URL 経由で取得")
    sp.add_argument("--save-html", help="トップページHTML原本の保存先(リポジトリ外・gitignore対象を推奨)")
    sp.set_defaults(fn=cmd_run)
    sp = sub.add_parser("merge-db")
    sp.add_argument("--master", default=str(mun.DEFAULT_MASTER)); sp.add_argument("--prefecture")
    sp.add_argument("--results", default="data/results"); sp.add_argument("--route", required=True); sp.add_argument("--db", default="out/crawl.sqlite")
    sp.set_defaults(fn=cmd_merge_db)
    sp = sub.add_parser("summarize")
    sp.add_argument("--results", default="data/results"); sp.add_argument("--route", required=True); sp.add_argument("--out", default="data/summary")
    sp.set_defaults(fn=cmd_summarize)
    sp = sub.add_parser("evaluate")
    sp.add_argument("--results", default="data/results"); sp.add_argument("--route", required=True); sp.add_argument("--truth", required=True)
    sp.set_defaults(fn=cmd_evaluate)
    sp = sub.add_parser("compare")
    sp.add_argument("--results", default="data/results"); sp.add_argument("routes", nargs="+")
    sp.set_defaults(fn=cmd_compare)

    sp = sub.add_parser("review-list")
    sp.add_argument("--master", default=str(mun.DEFAULT_MASTER)); sp.add_argument("--results", default="data/results")
    sp.add_argument("--out", default="data/review/v11"); sp.add_argument("routes", nargs="+")
    sp.set_defaults(fn=cmd_review_list)

    sp = sub.add_parser("redecide")
    sp.add_argument("--results", default="data/results"); sp.add_argument("--out", default="data/results")
    sp.add_argument("--route", required=True); sp.add_argument("--rules", default="v12.1")
    sp.add_argument("--from-routes", nargs="+", required=True); sp.add_argument("--compact", action="store_true")
    sp.set_defaults(fn=cmd_redecide)

    sp = sub.add_parser("survey"); add_select(sp)
    sp.add_argument("--from-route", required=True, help="入口にするハブ判定の結果のroute(例: redecide_v12_1)")
    sp.add_argument("--keywords", required=True, help="ワードの設定ファイル(config/keywords/*.json)")
    sp.add_argument("--route", default="local", help="この調査の実行ラベル(結果の保存先)")
    sp.add_argument("--results", default="data/results"); sp.add_argument("--out", default="data/survey")
    sp.add_argument("--max-pages", type=int, default=200); sp.add_argument("--depth", type=int, default=2)
    sp.add_argument("--workers", type=int, default=4); sp.add_argument("--interval", type=float, default=1.0)
    sp.add_argument("--use-proxy", action="store_true")
    sp.add_argument("--headless", action="store_true", help="JS描画のサイト(needs_headless)をヘッドレスブラウザで取得する(要 playwright)")
    sp.set_defaults(fn=cmd_survey)

    sp = sub.add_parser("survey-summary")
    sp.add_argument("--surveys", default="data/survey"); sp.add_argument("--keyword", required=True); sp.add_argument("--route", required=True)
    sp.add_argument("--out", default="data/summary")
    sp.set_defaults(fn=cmd_survey_summary)

    sp = sub.add_parser("ward-report")
    sp.add_argument("--master", default=str(mun.DEFAULT_MASTER)); sp.add_argument("--results", default="data/results")
    sp.add_argument("--out", default="data/summary"); sp.add_argument("--ward-routes", nargs="+", required=True)
    sp.add_argument("--parent-routes", nargs="+", required=True)
    sp.set_defaults(fn=cmd_ward_report)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
