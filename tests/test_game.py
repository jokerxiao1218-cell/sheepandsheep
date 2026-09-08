"""batch 2 测试:Game 门面(设计文档 §6.1-3/6/7、§6.2-8、§6.3-14/16、§6.4-17/18/19)。

两个重头用例:
- 第一关 100 局随机瞎点必胜(3 种图案 7 槽的鸽巢原理,§6.4-17);
- 第二关随机瞎点必输(地狱难度口径),输时槽恰好 7 张无三同(不变量)。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import random

import pytest

from game.core.cover import covered
from game.core.game import Game


def rollout(g, rng):
    """随机瞎点一整局,每步断言三消即时性不变量。"""
    steps = 0
    while g.status == "playing":
        ids = g.clickable_ids()
        assert ids, "场上还有牌却无可点牌——遮挡重算坏了"
        g.click(rng.choice(ids))
        cnt = {}
        for t in g.slot:
            cnt[t.type] = cnt.get(t.type, 0) + 1
        assert max(cnt.values(), default=0) <= 2, "槽内出现三同:三消没有即时发生"
        steps += 1
    return steps


# ---------------------------------------------------------------- §6.4-17

def test_level1_random_rollout_always_wins():
    for seed in range(100):
        g = Game(1, pattern_seed=seed)
        steps = rollout(g, random.Random(seed))
        assert g.status == "win", f"seed={seed} 第一关竟输了:鸽巢原理被破坏"
        assert g.snapshot()["gone"] == 36
        assert steps >= 12            # 36 张 = 至少 12 次三消


# ---------------------------------------------------------------- §6.4-18

def test_level2_random_rollout_loses():
    """第二关随机瞎点应几乎必输;输时槽 7 张、无三同。"""
    for seed in range(50):
        g = Game(2, pattern_seed=seed)
        rollout(g, random.Random(seed))
        if g.status == "lose":
            break
    assert g.status == "lose"
    assert len(g.slot) == 7
    cnt = {}
    for t in g.slot:
        cnt[t.type] = cnt.get(t.type, 0) + 1
    assert max(cnt.values()) <= 2, "输的瞬间槽里有三同:不该输的局输了"


# ---------------------------------------------------------------- §6.1-3/4

def test_click_moves_tile_and_eliminates():
    g = Game(2, pattern_seed=7)
    # 手挑三张同图案的明牌,验证完整链路:进槽-聚集-三消
    targets = [t for t in g.board_tiles() if t.clickable]
    by_type = {}
    for t in targets:
        by_type.setdefault(t.type, []).append(t)
    trip = next(v for v in by_type.values() if len(v) >= 3)[:3]
    r1 = g.click(trip[0].id)
    r2 = g.click(trip[1].id)
    r3 = g.click(trip[2].id)
    assert r1["ok"] and r2["ok"] and not r1["eliminated"] and not r2["eliminated"]
    assert r3["ok"] and len(r3["eliminated"]) == 3
    assert {t.type for t in r3["eliminated"]} == {trip[0].type}
    assert all(t.zone == "gone" for t in trip)
    assert g.snapshot()["slot"] == 0


def test_lose_on_seventh_without_match():
    """§6.2-8:第 7 张入槽无三消 → 立即判负。"""
    g = Game(2, pattern_seed=0)
    rng = random.Random(0)
    while g.status == "playing":
        before = len(g.slot)
        ids = g.clickable_ids()
        # 优先点槽里没有的图案(凑不齐,尽快满槽)
        fresh = [i for i in ids
                 if g._index[i].type not in {t.type for t in g.slot}]
        g.click(rng.choice(fresh or ids))
        if g.status == "lose":
            assert before == 6          # 第 7 张入槽瞬间
            break


# ---------------------------------------------------------------- §6.3-14

def test_click_covered_rejected():
    g = Game(2, pattern_seed=0)
    dim = next(t for t in g.board_tiles() if not t.clickable)
    r = g.click(dim.id)
    assert r["ok"] is False
    assert "压" in r["reason"]
    assert g.snapshot()["slot"] == 0    # 拒绝点没有副作用


def test_click_bad_id_raises():
    g = Game(1, pattern_seed=1)
    with pytest.raises(ValueError, match="没有这张牌"):
        g.click("不存在")


def test_click_after_over_raises():
    g = Game(1, pattern_seed=1)
    rng = random.Random(1)
    while g.status == "playing":
        g.click(rng.choice(g.clickable_ids()))
    with pytest.raises(ValueError, match="结束"):
        g.click(g.tiles[0].id)


def test_bad_level_and_mode():
    with pytest.raises(ValueError, match="没有这一关"):
        Game(9)
    with pytest.raises(ValueError, match="classic"):
        Game(1, mode="solvable")       # batch 4 接入,现在就该拒绝


# ---------------------------------------------------------------- §6.3-16 / §6.1-6

def test_zone_b_stack_top_only():
    g = Game(2, pattern_seed=0)
    top = g._index["B1-11"]
    below = g._index["B1-10"]
    deeper = g._index["B1-9"]
    assert top.clickable is True
    assert below.clickable is False
    assert deeper.visible == "hidden"
    r = g.click("B1-11")
    assert r["ok"]
    assert below.clickable is True      # 拿走顶后下一张变摞顶
    assert below.visible == "bright"
    assert deeper.visible == "dim"      # 更深处只被一张(新的顶)盖了


# ---------------------------------------------------------------- §6.1-5

def test_uncover_after_picking_blocker():
    """点走上层牌后,被它唯一压住的下层牌自动解锁。"""
    for seed in range(30):
        g = Game(2, pattern_seed=seed)
        board = g.board_tiles()
        for top in board:
            if not top.clickable:
                continue
            for low in board:
                if low.mold == 1 and low.layer < top.layer and covered(top, low):
                    blockers = [o for o in board
                                if o.layer > low.layer and covered(o, low)]
                    if blockers == [top] and not low.clickable:
                        assert g.click(top.id)["ok"]
                        assert low.clickable, \
                            f"seed={seed}:{top.id} 拿走后 {low.id} 应解锁"
                        return
    pytest.fail("30 个 seed 没找到唯一覆盖对——堆叠结构异常")


# ---------------------------------------------------------------- §6.5-21 前半

def test_click_at_logic():
    g = Game(2, pattern_seed=0)
    t = next(t for t in g.board_tiles() if t.clickable)
    assert g.click_at(t.rol, t.row)["ok"] is True      # 格坐标命中
    occupied = {(t.rol + dx, t.row + dy)
                for t in g.board_tiles() for dx in range(2) for dy in range(2)}
    empty = next((x, y) for x in range(12) for y in range(16)
                 if (x, y) not in occupied)
    assert g.click_at(*empty)["ok"] is False           # 空点没反应


# ---------------------------------------------------------------- §6.1-2

def test_three_visible_states_exist():
    g = Game(2, pattern_seed=0)
    states = {t.visible for t in g.board_tiles()}
    assert {"bright", "dim", "hidden"} <= states, f"22 层的塔里三态都该有:{states}"


def test_snapshot_shape():
    g = Game(1, pattern_seed=3)
    s = g.snapshot()
    assert s == {"level": "1", "mode": "classic", "status": "playing",
                 "board": 36, "slot": 0, "out": 0, "gone": 0,
                 "props": {"move_out": False, "shuffle": False, "undo": False}}
