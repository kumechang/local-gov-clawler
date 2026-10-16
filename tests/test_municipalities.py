from localgov_crawler import municipalities as mun


def test_load_master_normalizes_codes():
    items = mun.load()
    assert len(items) == 1918
    sapporo = next(m for m in items if m.name == "札幌市")
    assert sapporo.code == "01100" and sapporo.prefecture_code == "01"
    ward = next(m for m in items if m.full_name == "札幌市中央区")
    assert ward.parent_code == "01100" and ward.scope == "designated_city_ward"


def test_select_nara_has_39():
    sel = mun.select(mun.load(), prefecture="奈良県")
    assert len(sel) == 39
    assert len(mun.select(mun.load(), prefecture="29")) == 39


def test_shards_partition_and_keep_hosts_together():
    items = mun.load()
    n = 7
    shards = [mun.select(items, shard=(i, n)) for i in range(n)]
    codes = [m.code for s in shards for m in s]
    assert len(codes) == len(set(codes)) == len(items)
    host_to_shard = {}
    for i, s in enumerate(shards):
        for m in s:
            if m.host:
                assert host_to_shard.setdefault(m.host, i) == i


def test_scope_excludes_designated_city_wards():
    items = mun.load()
    plain = mun.select(items, scope="municipality")
    assert len(plain) == 1747 and all(m.scope == "municipality" for m in plain)
    assert len(mun.select(items, scope="designated_city_ward")) == 171
    osaka = mun.select(items, prefecture="大阪府", scope="municipality")
    assert len(osaka) == 43


def test_group_by_host_keeps_same_host_wards_together():
    """政令市の区は親市と同じホスト。1つのワーカーが順番に処理して、1ホスト1リクエスト/秒を守る(D-096)。"""
    from localgov_crawler.cli import group_by_host
    wards = mun.select(mun.load(), prefecture="大阪府", scope="designated_city_ward")
    groups = group_by_host(wards)
    assert len(wards) == 31 and sorted(len(g) for g in groups) == [7, 24]  # 大阪市24区と堺市7区(ホストが別)
    towns = mun.select(mun.load(), prefecture="奈良県")
    assert len(group_by_host(towns)) == len(towns)  # 通常の自治体はホストが別


def test_all_wards_share_the_parent_host():
    items = {m.code: m for m in mun.load()}
    wards = [m for m in items.values() if m.scope == "designated_city_ward"]
    assert len(wards) == 171 and all(m.host == items[m.parent_code].host for m in wards)
