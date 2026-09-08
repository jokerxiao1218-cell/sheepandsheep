"""batch 4 测试:逆向构造 + 回溯求解(设计文档 §6.2-12、§6.4)。

deal_solvable 的核心验收:构造出的局,把返回的序列按顺序点回去必须通关
(构造即证明);每种图案张数恒为 组数×3。
solve 的核心验收:解出的序列回放必须通关;绝不修改传入的局。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import time

import pytest

from game.core.game import Game
from game.core.solver import SolveBudget, deal_solvable, solve
from game.core.tiles import load_levels, make_skeleton


LEVELS = load_levels()


def replay(g, seq):
    for tid in seq:
        r = g.click(tid)
        assert r["ok"], f"序列 {tid} 不可点:构造/求解器有 bug"
    return g.status


# ---------------------------------------------------------------- §6.2-12

@pytest.mark.parametrize("level,seeds", [(1, range(10)), (2, range(5))])
def test_deal_solvable_replays_win(level, seeds):
    for seed in seeds:
        g = Game(level, mode="solvable", pattern_seed=seed)
        assert len(g.solution) == len(g.tiles), "每张牌点恰好一次"
        assert replay(g, g.solution) == "win"


def test_deal_solvable_distribution():
    """每种图案张数恒为 组数×3(数量约束在构造模式下也必须成立)。"""
    p = LEVELS["2"]
    sk = make_skeleton(p, p["skeleton_seed"])
    deal_solvable(sk, p["block_type_data"], pattern_seed=2022)
    dist = {}
    for t in sk:
        dist[t.type] = dist.get(t.type, 0) + 1
    expect = {int(k): v * 3 for k, v in p["block_type_data"].items()}
    assert dist == expect


def test_deal_solvable_deterministic():
    p = LEVELS["1"]
    a = make_skeleton(p, 1)
    seq_a = deal_solvable(a, p["block_type_data"], pattern_seed=77)
    types_a = [t.type for t in a]
    b = make_skeleton(p, 1)
    seq_b = deal_solvable(b, p["block_type_data"], pattern_seed=77)
    assert seq_a == seq_b and types_a == [t.type for t in b]


def test_deal_solvable_random_seed():
    """pattern_seed=None 走 Game 路径:随机种子也能构造并回放通关。"""
    g = Game(1, mode="solvable")
    assert replay(g, g.solution) == "win"


def test_deal_solvable_bad_counts():
    p = LEVELS["1"]
    sk = make_skeleton(p, 1)
    bad = {"1": 4, "2": 4, "3": 5}       # 13 组 ≠ 骨架 36/3=12 组
    with pytest.raises(ValueError, match="不一致"):
        deal_solvable(sk, bad, pattern_seed=1)


# ---------------------------------------------------------------- 回溯求解

def test_solve_level1_and_replay():
    g = Game(1, pattern_seed=11)
    before = g.snapshot()
    seq = solve(g, SolveBudget(max_nodes=200_000, time_limit=10.0))
    assert seq is not None, "第一关鸽巢必胜,求解器不该找不到"
    assert g.snapshot() == before            # 求解绝不修改原局
    g2 = Game(1, pattern_seed=11)
    for tid in seq:                           # 解出的序列原局回放必胜
        assert g2.click(tid)["ok"]
    assert g2.status == "win"


def test_solve_respects_budget():
    """第二关经典局预算收紧:要么出解要么如实 None,且不许超预算太多。"""
    g = Game(2, pattern_seed=0)
    before = g.snapshot()
    start = time.monotonic()
    seq = solve(g, SolveBudget(max_nodes=20_000, time_limit=2.0))
    spent = time.monotonic() - start
    assert spent < 5.0                        # 时间预算大致被尊重
    assert g.snapshot() == before            # 原局不动
    if seq is not None:                        # 万一真解出来了,回放必须赢
        g2 = Game(2, pattern_seed=0)
        for tid in seq:
            assert g2.click(tid)["ok"]
        assert g2.status == "win"


def test_solve_with_out_zone_returns_none():
    """移出区有牌:不搜,如实返回 None。构造是固定 seed 的确定性操作,
    前提必须硬断言——曾用恒真 else 兜底,构造失败时这个唯一覆盖会静默消失。"""
    g = Game(2, pattern_seed=0)
    picked_types = set()                       # 只点互不同图案的明牌:不可能三消
    for t in g.board_tiles():
        if t.clickable and t.type not in picked_types:
            g.click(t.id)
            picked_types.add(t.type)
        if len(g.slot) >= 3:
            break
    assert len(g.slot) == 3, "3 张异图案明牌凑不进槽:构造前提坏了"
    assert g.use_prop("move_out") is True       # 前提失败要大声红,不许静默绿
    assert solve(g) is None                     # 有牌困在移出区:不搜,如实说


def test_solve_respects_node_budget():
    """max_nodes 维度独立钉死:节点预算远小于时间预算时必须先触发
    (回归:曾只验时间维度,节点检查失效被时间预算兜底掩盖)。"""
    g = Game(2, pattern_seed=0)
    before = g.snapshot()
    start = time.monotonic()
    seq = solve(g, SolveBudget(max_nodes=50, time_limit=60.0))
    spent = time.monotonic() - start
    assert spent < 5.0                        # 50 个节点微秒级,远早于时间预算
    assert seq is None                         # 第二关 88 组消除,50 节点内到不了
    assert g.snapshot() == before              # 原局不动


def test_solve_finished_game_returns_none():
    g = Game(1, mode="solvable", pattern_seed=1)
    for tid in g.solution:
        g.click(tid)
    assert g.status == "win"
    assert solve(g) is None
