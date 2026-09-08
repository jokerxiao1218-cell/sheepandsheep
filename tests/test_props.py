"""batch 3 测试:三道具与撤销历史(设计文档 §6.2-10/11/13、§6.1-13)。

效果口径全部来自原版反编译(§3.1):移出=槽头 3 张进移出区+清撤销历史、
撤销=退回最后进槽的那张(跨消除不可撤)、洗牌=只重排场上牌的图案位置不动。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import random

import pytest

from game.core.game import Game
from game.core.props import move_out, shuffle_tiles, undo_pop
from game.core.tiles import Tile


def mk(tid, type_):
    return Tile(id=tid, type=type_)


# ---------------------------------------------------------------- 纯函数层

def test_move_out_takes_first_three_and_clears_history():
    slot = [mk("a", 1), mk("b", 2), mk("c", 3), mk("d", 4)]
    out = []
    history = [("a", "board"), ("b", "board")]
    moved = move_out(slot, out, history)
    assert [t.id for t in moved] == ["a", "b", "c"]    # 槽头顺序 3 张
    assert [t.id for t in slot] == ["d"]
    assert [t.id for t in out] == ["a", "b", "c"]
    assert history == []                                # 撤销历史被清空


def test_move_out_insufficient_slot_noop():
    slot = [mk("a", 1), mk("b", 2)]
    out = []
    history = [("a", "board")]
    assert move_out(slot, out, history) is None          # 不足 3 张:全都不动
    assert [t.id for t in slot] == ["a", "b"]
    assert out == []
    assert history == [("a", "board")]


def test_shuffle_tiles_only_board_types():
    rng = random.Random(1)
    b1 = mk("b1", 1)
    b2 = mk("b2", 1)
    b3 = mk("b3", 2)
    s1 = mk("s1", 3)
    s1.zone = "slot"
    g1 = mk("g1", 3)
    g1.zone = "gone"
    before = [(t.id, t.rol, t.row, t.layer) for t in (b1, b2, b3)]
    types_before = sorted(t.type for t in (b1, b2, b3))
    shuffle_tiles([b1, b2, b3, s1, g1], rng)
    assert sorted(t.type for t in (b1, b2, b3)) == types_before  # 多重集合不变
    assert [(t.id, t.rol, t.row, t.layer) for t in (b1, b2, b3)] == before  # 位置不动
    assert s1.type == 3 and g1.type == 3                # 槽/已消不参与


def test_undo_pop_lifo():
    assert undo_pop([]) is None
    history = [("a", "board"), ("b", "out")]
    assert undo_pop(history) == ("b", "out")            # 后进先出
    assert undo_pop(history) == ("a", "board")
    assert undo_pop(history) is None


# ---------------------------------------------------------------- Game 集成

def fresh_game_with_slot(n):
    """开一局第二关并点 n 张明牌进槽(不触发三消),返回 (game, 点过的牌)。"""
    g = Game(2, pattern_seed=0)
    picked = []
    for t in g.board_tiles():
        if len(picked) == n:
            break
        if t.clickable and t.type not in {p.type for p in picked}:
            # 只点互不同图案的牌,保证不三消
            if sum(1 for p in picked if p.type == t.type) == 0 and t.clickable:
                g.click(t.id)
                picked.append(t)
    return g, picked


def test_move_out_prop_flow():
    g, picked = fresh_game_with_slot(3)
    assert len(g.slot) == 3
    assert g.use_prop("move_out") is True
    assert len(g.slot) == 0
    assert all(t.zone == "out" for t in picked)
    assert g.prop_used["move_out"] is True
    assert g.use_prop("move_out") is False               # 每局只 1 次


def test_move_out_insufficient_slot_keeps_prop():
    g, _ = fresh_game_with_slot(2)
    assert g.use_prop("move_out") is False               # 槽 2 张:不动
    assert g.prop_used["move_out"] is False             # 道具没被消耗
    g2, _ = fresh_game_with_slot(3)
    assert g2.use_prop("move_out") is True               # 槽 3 张时还能用


def test_move_out_clears_undo_history():
    g, _ = fresh_game_with_slot(4)
    assert len(g.history) == 4
    assert g.use_prop("move_out") is True
    assert g.history == []                               # 反编译口径:移出清撤销历史


def test_out_zone_click_back_and_undo():
    """移出区的牌点回槽(合法);撤销时退回移出区而非场上。"""
    g, picked = fresh_game_with_slot(3)
    assert g.use_prop("move_out") is True
    first = picked[0]
    r = g.click(first.id)                               # 点移出区的牌
    assert r["ok"] is True and len(g.slot) == 1
    assert first.zone == "slot"
    assert g.history == [(first.id, "out")]              # 来源记为移出区
    g2, picked2 = fresh_game_with_slot(3)
    g2.use_prop("move_out")
    g2.click(picked2[0].id)
    g2.use_prop("undo")                                  # undo 在另一局用(每局 1 次)
    assert picked2[0].zone == "out"                      # 撤回到移出区原位


def test_undo_returns_tile_to_board():
    g, picked = fresh_game_with_slot(1)
    tile = picked[0]
    assert g.use_prop("undo") is True
    assert tile.zone == "board"                          # 回场上原位
    assert len(g.slot) == 0
    assert tile.clickable is True                        # 回去后仍可点
    assert g.prop_used["undo"] is True
    assert g.use_prop("undo") is False                   # 免费撤销每局 1 次
    r = g.click(tile.id)                                 # 还能再点回去
    assert r["ok"] is True


def test_undo_after_elimination_blocked():
    """三消清空撤销历史:跨消除不可撤。"""
    g = Game(2, pattern_seed=7)
    targets = [t for t in g.board_tiles() if t.clickable]
    by_type = {}
    for t in targets:
        by_type.setdefault(t.type, []).append(t)
    trip = next(v for v in by_type.values() if len(v) >= 3)[:3]
    for t in trip:
        g.click(t.id)                                   # 第 3 张触发三消
    assert all(t.zone == "gone" for t in trip)
    assert g.history == []
    assert g.use_prop("undo") is False                   # 没有可撤的步


def test_undo_zone_b_stack_top():
    """撤销 B 区摞顶:牌回摞顶,下一张重新被盖住。"""
    g = Game(2, pattern_seed=0)
    top = g._index["B1-11"]
    below = g._index["B1-10"]
    assert g.click("B1-11")["ok"] is True
    assert below.clickable is True
    assert g.use_prop("undo") is True
    assert top.zone == "board" and top.clickable is True
    assert below.clickable is False                      # 摞顶回来了


def test_shuffle_prop_keeps_everything_but_types():
    g, _ = fresh_game_with_slot(3)
    assert g.use_prop("move_out") is True                # 顺带让槽/移出区有牌
    board = g.board_tiles()
    before = {t.id: t.type for t in board}
    all_types_before = sorted(t.type for t in board)
    g.click(g.board_tiles()[0].id)                      # 槽里再有一张
    slot_snapshot = [(t.id, t.type) for t in g.slot]
    out_snapshot = [(t.id, t.type) for t in g.out_zone]
    assert g.use_prop("shuffle") is True
    after = {t.id: t.type for t in board}
    assert sorted(after.values()) == all_types_before   # 图案多重集合不变
    changed = sum(1 for k in before if before[k] != after[k])
    assert changed >= 10                                 # 264 张里必然大换
    assert slot_snapshot == [(t.id, t.type) for t in g.slot]     # 槽不动
    assert out_snapshot == [(t.id, t.type) for t in g.out_zone]  # 移出区不动
    assert g.prop_used["shuffle"] is True
    assert g.use_prop("shuffle") is False


def test_out_zone_blocks_win():
    """§6.2-10:场上+槽全空但移出区有牌 → 不算赢;点回消完才算赢。"""
    g = Game(1, pattern_seed=5)
    by_type = {}
    for t in g.tiles:
        by_type.setdefault(t.type, []).append(t)
    trio = next(v for v in by_type.values() if len(v) >= 3)[:3]
    # 白盒构造:除 trio 外全部已消,槽空,trio 三张同图案牌在移出区
    for t in g.tiles:
        t.zone = "gone" if t not in trio else "out"
    g.slot.clear()
    g.out_zone.extend(trio)
    # 逐张点回:前两张时"移出区还有牌"不该判赢,第三张三消后才算通关
    assert g.click(trio[0].id)["ok"] is True
    assert g.status == "playing"                       # 移出区还有 2 张:没赢
    assert g.click(trio[1].id)["ok"] is True
    assert g.status == "playing"                       # 还差最后 1 张
    assert g.click(trio[2].id)["ok"] is True
    assert g.status == "win"                           # 全消完才是赢


def test_use_prop_bad_args():
    g = Game(1, pattern_seed=1)
    with pytest.raises(ValueError, match="没有这种道具"):
        g.use_prop("复活")
    with pytest.raises(ValueError, match="没有这种道具"):
        g.use_prop("move_out2")
    rng = random.Random(1)
    while g.status == "playing":
        g.click(rng.choice(g.clickable_ids()))
    with pytest.raises(ValueError, match="结束"):
        g.use_prop("shuffle")
