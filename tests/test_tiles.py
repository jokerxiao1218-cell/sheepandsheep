"""batch 1 测试:关卡参数校验、层曲线、骨架生成、原味发牌(设计文档 §6.1-1/2、§6.3-15)。

重叠判定在测试里独立按 |Δrol|<2 且 |Δrow|<2 复算(不 import 实现里的
_overlap)——覆盖公式本身也被测试钉死:实现要是和契约不一致,这里会红。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import json
import time

import pytest

from game.core import tiles
from game.core.tiles import LevelError, deal_random, load_levels, make_skeleton


def overlap(rol_a, row_a, rol_b, row_b):
    """契约 §5.2 的 AABB 重叠公式(独立复算)。"""
    return abs(rol_a - rol_b) < 2 and abs(row_a - row_b) < 2


@pytest.fixture(scope="module")
def levels():
    return load_levels()


L1, L2 = "1", "2"


def tile_key(t):
    """逐字段快照(复现性断言用)。"""
    return (t.id, t.rol, t.row, t.layer, t.type, t.mold, t.zone)


def assert_layer_invariants(a_tiles):
    """A 区不变量:层号连续、同层两两不重叠、整体有堆叠感(≥50% 的牌与异层
    牌重叠——倒生长 STACK_BIAS=0.75 摞邻域的直接结果,防"塔散成平铺")。"""
    by_layer = {}
    for t in a_tiles:
        by_layer.setdefault(t.layer, []).append(t)
    assert sorted(by_layer) == list(range(1, len(by_layer) + 1)), "层号必须从 1 连续"
    for layer, group in sorted(by_layer.items()):
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                assert not overlap(a.rol, a.row, b.rol, b.row), \
                    f"层 {layer} 同层重叠:{a.id} × {b.id}"
    stacked = sum(
        1 for a in a_tiles
        if any(a.layer != b.layer and overlap(a.rol, a.row, b.rol, b.row) for b in a_tiles)
    )
    assert stacked >= len(a_tiles) * 0.5, \
        f"堆叠密度 {stacked}/{len(a_tiles)} 低于 50%:骨架散成平铺,不是塔"


# ---------------------------------------------------------------- §6.1-1 参数

def test_levels_ok(levels):
    assert set(levels) == {L1, L2}
    assert levels[L1]["block_type_data"] == {"1": 4, "2": 4, "3": 4}
    assert levels[L2]["block_type_data"] == {str(i): 6 for i in range(1, 14)} | {"14": 5, "15": 5}


def test_levels_bad_json(tmp_path):
    bad = tmp_path / "levels.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(LevelError, match="JSON"):
        load_levels(bad)


def test_levels_missing_file(tmp_path):
    with pytest.raises(LevelError, match="读不了"):
        load_levels(tmp_path / "nope.json")


def test_levels_deal_skeleton_mismatch(tmp_path):
    """§6.3-15:图案张数与骨架牌数对不上,必须在读关卡时就拦下。"""
    raw = load_levels()
    raw[L1]["block_type_data"]["3"] = 5          # 13 组×3=39 ≠ 骨架 36
    bad = tmp_path / "levels.json"
    bad.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LevelError, match=r"39.*36"):
        load_levels(bad)


def test_levels_bad_zone_b(tmp_path):
    """zone_b 摞位越界要拦:B 区摞位置出网格右边界。"""
    raw = load_levels()
    raw[L1]["zone_b"] = {"stacks": 1, "per_stack": 3, "rol": [9], "row": 5}
    # 第一关 cols=10,合法 rol ∈ [0,8];9 越界 → 报错。牌数也对不上(9 vs 36)
    # 但 rol 越界先炸,这个用例只验 rol 分支。
    bad = tmp_path / "levels.json"
    bad.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LevelError, match="越界"):
        load_levels(bad)


def test_levels_peak_below_edge(tmp_path):
    raw = load_levels()
    raw[L1]["zone_a"]["peak_count"] = 2           # peak_count < edge=10 → 参数自相矛盾
    bad = tmp_path / "levels.json"
    bad.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LevelError, match="peak_count"):
        load_levels(bad)


# ---------------------------------------------------------------- 层曲线

def test_layer_counts_level1(levels):
    assert tiles._make_layer_counts(levels[L1]["zone_a"]) == [10, 16, 10]


def test_layer_counts_level2(levels):
    counts = tiles._make_layer_counts(levels[L2]["zone_a"])
    assert len(counts) == 22
    assert sum(counts) == 242          # A 区总张数(与抓包 264-22 吻合)
    assert max(counts) == 18           # 峰值 = peak_count
    assert abs(counts.index(18) + 1 - 11) <= 2   # 峰落在 peak_layer=11 附近


def test_layer_counts_rejects_impossible():
    za = {"layers": 22, "total": 10, "peak_layer": 11, "peak_count": 18, "edge": 4}
    with pytest.raises(LevelError, match="凑不出"):
        tiles._make_layer_counts(za)


# ---------------------------------------------------------------- 骨架 §6.1-1

def test_skeleton_level1(levels):
    p = levels[L1]
    t1 = make_skeleton(p, p["skeleton_seed"])
    assert len(t1) == 36
    assert {t.layer for t in t1} == {1, 2, 3}
    assert all(t.mold == 1 and t.zone == "board" and t.type == 0 for t in t1)
    assert len({t.id for t in t1}) == 36                       # id 唯一
    za = p["zone_a"]
    assert all(0 <= t.rol <= za["cols"] - 2 and 0 <= t.row <= za["rows"] - 2 for t in t1)
    assert_layer_invariants(t1)
    # 同 seed 完全复现
    again = make_skeleton(p, p["skeleton_seed"])
    assert [tile_key(t) for t in t1] == [tile_key(t) for t in again]


def test_skeleton_level2(levels):
    p = levels[L2]
    t2 = make_skeleton(p, p["skeleton_seed"])
    assert len(t2) == 264
    a = [t for t in t2 if t.mold == 1]
    b = [t for t in t2 if t.mold == 2]
    assert len(a) == 242 and len(b) == 22
    assert {t.layer for t in a} == set(range(1, 23))            # 22 层连续
    assert_layer_invariants(a)
    # 明牌是涌现属性:第一层(最底层)牌最少,开局可点牌来自各层露出的表面
    first_layer = [t for t in a if t.layer == 1]
    assert len(first_layer) == 4                                # edge=4
    # B 区:2 摞各 11 张,同摞同 (rol,row),层号 1..11
    zb = p["zone_b"]
    for s in range(1, zb["stacks"] + 1):
        stack = [t for t in b if t.id.startswith(f"B{s}-")]
        assert len(stack) == 11
        assert {t.rol for t in stack} == {zb["rol"][s - 1]}
        assert {t.row for t in stack} == {zb["row"]}
        assert sorted(t.layer for t in stack) == list(range(1, 12))
    again = make_skeleton(p, p["skeleton_seed"])
    assert [tile_key(t) for t in t2] == [tile_key(t) for t in again]


def test_skeleton_fast_enough(levels):
    """拒绝采样不许死循环:第二关骨架连续生成 20 次 3 秒内完成。"""
    start = time.monotonic()
    for i in range(20):
        make_skeleton(levels[L2], 1000 + i)
    assert time.monotonic() - start < 3.0


# ---------------------------------------------------------------- 发牌 §6.1-2

def test_deal_random_distribution(levels):
    """每种图案张数恒为 组数×3(第一关 3 种各 12 张)。"""
    p = levels[L1]
    sk = make_skeleton(p, 1)
    deal_random(sk, p["block_type_data"], pattern_seed=42)
    dist = {}
    for t in sk:
        dist[t.type] = dist.get(t.type, 0) + 1
    assert dist == {1: 12, 2: 12, 3: 12}


def test_deal_random_deterministic(levels):
    p = levels[L1]
    sk_a = make_skeleton(p, 99)
    deal_random(sk_a, p["block_type_data"], pattern_seed=7)
    sk_b = make_skeleton(p, 99)
    deal_random(sk_b, p["block_type_data"], pattern_seed=7)
    sk_c = make_skeleton(p, 99)
    deal_random(sk_c, p["block_type_data"], pattern_seed=8)
    assert [t.type for t in sk_a] == [t.type for t in sk_b]      # 同 seed 复现
    assert [t.type for t in sk_a] != [t.type for t in sk_c]      # 异 seed 不同


def test_deal_random_live_seed(levels):
    """pattern_seed=None(真随机)也必须跑通且数量恒对。"""
    p = levels[L1]
    sk = make_skeleton(p, 1)
    deal_random(sk, p["block_type_data"])
    assert sum(1 for t in sk if t.type in (1, 2, 3)) == 36


def test_deal_random_mismatch_raises(levels):
    sk = make_skeleton(levels[L1], 1)
    btd = {"1": 4, "2": 4, "3": 4, "9": 4}      # 16 组×3=48 ≠ 骨架 36
    with pytest.raises(ValueError, match=r"48.*36"):
        deal_random(sk, btd, pattern_seed=1)
