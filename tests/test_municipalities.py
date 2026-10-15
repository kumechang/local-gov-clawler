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
