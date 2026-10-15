"""コマンドライン。run / merge-db / summarize / evaluate / compare / list。"""
from __future__ import annotations

import argparse
import json
import os
import sys
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

    # 並列化は自治体単位。ワーカーごとにFetcherを持つので、同じ自治体に複数リクエストが同時に当たらない
    def work(m):
        f = Fetcher(user_agent=build_user_agent(contact), proxy=proxy, min_interval=args.interval)
        try:
            return m, analyze(m, f, cfg)
        finally:
            f.close()

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(work, m) for m in sel]
        for fut in as_completed(futures):
            m, res = fut.result()
            store.write_result(out, res, m.prefecture_code, compact=args.compact)
            done += 1
            print(f"[{done}/{len(sel)}] {m.code} {m.name}: {res['outcome']} {res['failure_class']}".strip(), flush=True)
    return 0


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
    sp.add_argument("--compact", action="store_true", help="軽量形式で保存(サイト内リンク一覧を捨てる。全国実行用、D-062)")
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

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
