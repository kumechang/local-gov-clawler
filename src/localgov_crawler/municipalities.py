"""自治体マスタCSVの読み込みと対象の絞り込み・シャード分割。"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_MASTER = Path("data/input/municipalities_master.csv")


@dataclass(frozen=True)
class Municipality:
    code: str  # 5桁の地方公共団体コード(チェックデジットなし)
    name: str
    full_name: str
    prefecture_code: str  # 2桁
    prefecture_name: str
    kind: str  # city / town / village / designated_city / designated_city_ward / special_ward
    scope: str  # municipality / designated_city_ward
    parent_code: str
    url: str
    xml_sitemap_url: str
    xml_sitemap_candidate_url: str

    @property
    def host(self) -> str:
        return (urlsplit(self.url).hostname or "").lower()


def _code(value: str, width: int) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return f"{int(float(value)):0{width}d}"


def load(path: str | Path = DEFAULT_MASTER) -> list[Municipality]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append(
            Municipality(
                code=_code(r["municipality_code"], 5),
                name=r["municipality_name"],
                full_name=r["municipality_full_name"],
                prefecture_code=_code(r["prefecture_code"], 2),
                prefecture_name=r["prefecture_name"],
                kind=r["municipality_type"],
                scope=r["record_scope"],
                parent_code=_code(r["parent_municipality_code"], 5),
                url=(r["official_website_url"] or "").strip(),
                xml_sitemap_url=(r["xml_sitemap_url"] or "").strip(),
                xml_sitemap_candidate_url=(r["xml_sitemap_candidate_url"] or "").strip(),
            )
        )
    return out


def select(
    items: list[Municipality],
    prefecture: str | None = None,
    codes: list[str] | None = None,
    shard: tuple[int, int] | None = None,
) -> list[Municipality]:
    """prefectureは名称('奈良県')または2桁コード('29')。shardは(index, total)。"""
    if prefecture:
        items = [m for m in items if prefecture in (m.prefecture_name, m.prefecture_code)]
    if codes:
        wanted = set(codes)
        items = [m for m in items if m.code in wanted]
    if shard:
        items = _shard(items, *shard)
    return items


def _shard(items: list[Municipality], index: int, total: int) -> list[Municipality]:
    """同一ホストは同じシャードに入れる(政令市の区などで同じサーバーへ同時に当たらないため)。"""
    if not 0 <= index < total:
        raise ValueError(f"shard index {index} out of range for total {total}")
    groups: dict[str, list[Municipality]] = {}
    for m in items:
        groups.setdefault(m.host or f"_nohost_{m.code}", []).append(m)
    loads = [0] * total
    assigned: dict[str, int] = {}
    # 大きいグループから最小負荷のシャードへ入れる(決定的)
    for host, g in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        i = min(range(total), key=lambda k: (loads[k], k))
        loads[i] += len(g)
        assigned[host] = i
    return [m for h, g in sorted(groups.items()) for m in g if assigned[h] == index]
