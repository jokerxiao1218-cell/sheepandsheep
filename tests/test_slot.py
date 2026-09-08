"""batch 2 测试:7 槽位聚集插入/三消/满判定(设计文档 §6.1-3/4、§6.2-9)。

聚集插入的真值表全部手推(§6 计划),A/B/C 是三种图案(1/2/3)。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import random

import pytest

from game.core.slot import SLOT_SIZE, insert, is_full, would_lose
from game.core.tiles import Tile

A, B, C, D = 1, 2, 3, 4


def mk(tid, type_):
    return Tile(id=tid, type=type_)


def slot_of(types):
    return [mk(f"s{i}", t) for i, t in enumerate(types)]


# (槽内图案序列, 进槽图案, 期望槽结果, 期望消除张数)
INSERT_TABLE = [
    ([],       A, [A],             0),   # 空槽
    ([A],      A, [A, A],          0),   # 聚集挨着
    ([A, B],   A, [A, A, B],       0),   # 插到最后一张同图案后
    ([A, B],   B, [A, B, B],       0),
    ([A, B],   C, [A, B, C],       0),   # 无同图案 → 插槽尾
    ([B, A],   A, [B, A, A],       0),
    ([B, A, A], A, [B],            3),   # 第 3 张瞬间消,槽只剩异类
    ([A, A, B], A, [B],            3),
    ([A, A, B, B], A, [B, B],      3),   # 聚集插入后三连消
    ([A, B, A], A, [B],            3),   # 同图案被隔开时,新牌聚集到后面凑满
]


@pytest.mark.parametrize("start,inc,expect,elim_n", INSERT_TABLE)
def test_insert_table(start, inc, expect, elim_n):
    slot = slot_of(start)
    tile = mk("x", inc)
    eliminated = insert(slot, tile)
    assert [t.type for t in slot] == expect
    assert len(eliminated) == elim_n
    if eliminated:
        assert {t.type for t in eliminated} == {inc}


def test_insert_same_type_never_exceeds_two():
    """三消即时性不变量:任意时刻槽内同图案 ≤2(§6.4-19)。"""
    rng = random.Random(20220924)
    for _ in range(300):
        slot = slot_of([])
        for _ in range(40):
            insert(slot, mk("x", rng.randint(1, 8)))
            cnt = {}
            for t in slot:
                cnt[t.type] = cnt.get(t.type, 0) + 1
            assert max(cnt.values(), default=0) <= 2, f"槽内出现三同:{cnt}"


def test_is_full():
    assert is_full(slot_of([])) is False
    assert is_full(slot_of([A, B, A, B, C, A])) is False     # 6 张
    assert is_full(slot_of([A, B, A, B, C, A, B])) is True   # 7 张


def test_would_lose():
    six_pair = slot_of([A, A, B, B, C, C])       # 6 张,三对
    assert would_lose(six_pair, mk("x", A)) is False      # 第 3 张 → 消,不输
    assert would_lose(six_pair, mk("x", D)) is True       # 第 7 张新图案 → 输
    five = slot_of([A, A, B, B, C])
    assert would_lose(five, mk("x", D)) is False          # 槽 5 张怎么点都不输
    lone_pair = slot_of([A, A, B, B, C, D])      # 6 张
    assert would_lose(lone_pair, mk("x", A)) is False     # A 已 2 张,第 3 张进槽即消
    assert would_lose(lone_pair, mk("x", C)) is True       # C 只 1 张,第 7 张占满判负


def test_slot_size_is_seven():
    assert SLOT_SIZE == 7
