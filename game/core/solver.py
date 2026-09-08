"""求解与逆向构造(设计文档 §3.4 / §4.4 / §5.2 模块 M6)。

两件事:
1. deal_solvable 逆向构造"必可解"的图案分布:随机模拟一遍聪明玩家的拿牌
   顺序(每步从可点牌里随机挑一张、给牌分配临时"组号",槽内复用真实的
   聚集/三消逻辑),88 个组号再映射到真实图案——拿牌顺序本身就是一条通关
   路径,构造即证明,不需要任何搜索(业界无公开先例,自研思路,§3.4);
2. solve 回溯求解:DFS + 状态指纹去重 + "优先点槽内已凑 2 张"的启发式排序,
   限时限节点,超时如实返回 None——广义三消可解性是 NP-hard
   (arXiv:1403.5830),不承诺任意局必解。不修改传入的 game(克隆状态搜)。
"""
import random
import time

from .cover import refresh_cover
from .slot import insert as _insert, would_lose
from .tiles import Tile

# 逆向构造的重试上限:模拟死路(槽 6 张凑不出第三张)换 attempt 重来
MAX_BUILD_TRIES = 200


class SolveBudget:
    """回溯求解的预算:节点数与秒数,任一超限即中止并如实返回 None。"""

    def __init__(self, max_nodes=200_000, time_limit=10.0):
        self.max_nodes = max_nodes
        self.time_limit = time_limit


class _BudgetOut(Exception):
    """预算耗尽的内部信号(转成 None 返回,不外泄异常)。"""


# ---------------------------------------------------------------- 逆向构造

def deal_solvable(tiles, block_type_data, pattern_seed):
    """逆向构造必可解的图案分布(原地填 tiles 的 type),返回通关点击序列。

    pattern_seed 传死值完全可复现。构造不出来(多次死路)抛 RuntimeError。
    """
    n_groups = sum(block_type_data.values())
    if n_groups * 3 != len(tiles):
        raise ValueError(
            f"图案 {n_groups} 组×3={n_groups * 3} 张与骨架 {len(tiles)} 张不一致"
        )
    for attempt in range(MAX_BUILD_TRIES):
        rng = random.Random(pattern_seed * 1000 + attempt)
        seq = _try_build(tiles, block_type_data, rng)
        if seq is not None:
            return seq
    raise RuntimeError(
        f"逆向构造 {MAX_BUILD_TRIES} 次全部死路:拿牌策略需要调整(或骨架太挤)"
    )


def _try_build(tiles, block_type_data, rng):
    """一次构造尝试:成功回写真实图案并返回序列;死路返回 None(不动 tiles)。"""
    # 模拟副本:不动调用方的牌;构造成功才回写
    sim = [Tile(id=t.id, rol=t.rol, row=t.row, layer=t.layer, mold=t.mold,
                zone="board") for t in tiles]
    index = {t.id: t for t in sim}
    slot = []
    next_group = 1
    seq = []
    board_left = len(sim)
    while board_left:
        refresh_cover(sim)
        clickable = [t for t in sim if t.zone == "board" and t.clickable]
        tile = clickable[rng.randrange(len(clickable))]
        # 组号分配——核心不变量:board_left − open_need(未完成组还差的张数)
        # 恒为 3 的倍数且 ≥0。开新组只会在这个差 ≥3 时发生,于是终态必然
        # board_left == open_need == 0:每张牌都精确填进一个能凑齐的组,
        # "牌拿完了槽里还剩凑不齐的组"这种死路在结构上不可达。
        counts = {}
        for s in slot:
            counts[s.type] = counts.get(s.type, 0) + 1
        open_need = sum(3 - c for c in counts.values())
        twos = [g for g, c in counts.items() if c == 2]
        ones = [g for g, c in counts.items() if c == 1]
        if twos:
            # 已凑 2 张的组:第 3 张进槽立即消(最优先——永远不让槽越堆越长)
            group = twos[rng.randrange(len(twos))]
        elif board_left - open_need >= 3 and len(slot) <= 3:
            # 供给充足且槽很短才开新组;槽 ≥4 后只凑对/消,"槽 6 张却没有任何
            # 2 张组"的满槽死局同样结构上不可达
            group = next_group
            next_group += 1
        elif ones:
            group = ones[rng.randrange(len(ones))]    # 凑对(1 张 → 2 张)
        else:
            return None    # 开不了新组又没有可凑的组:防御(不变量上不可达)
        tile.type = group
        tile.zone = "slot"
        seq.append(tile.id)
        for e in _insert(slot, tile):                 # 复用真实聚集/三消逻辑
            e.zone = "gone"
        board_left -= 1
    if slot:
        return None            # 牌拿完了槽还剩:尾组凑不齐,换一次重试
    # 组号 → 图案映射:每种图案分到的组数必须与 block_type_data 完全一致
    pool = []
    for tid, groups in block_type_data.items():
        pool.extend([int(tid)] * groups)
    if len(pool) != next_group - 1:
        raise ValueError(
            f"构造组数 {len(pool)} 与实际用掉的 {next_group - 1} 不一致——数据坏了"
        )
    rng.shuffle(pool)
    group_to_type = {g: pool[i] for i, g in enumerate(range(1, next_group))}
    for orig, s in zip(tiles, sim):
        orig.type = group_to_type[s.type]
    return seq


# ---------------------------------------------------------------- 回溯求解

def solve(game, budget=None):
    """回溯求解"不用道具能否通关",返回点击序列;预算内没能证明返回 None。

    只搜"点场上牌"的动作(SheepSolver 同口径不用道具);移出区有牌的局
    直接 None(那是道具造成的局面,不归这个工具管)。绝不修改传入的 game。
    """
    if game.out_zone:
        return None
    if game.status != "playing":
        return None
    budget = budget or SolveBudget()
    tiles = [Tile(id=t.id, rol=t.rol, row=t.row, layer=t.layer, type=t.type,
                  mold=t.mold, zone=t.zone) for t in game.tiles]
    index = {t.id: t for t in tiles}
    start_slot = [index[t.id] for t in game.slot]
    deadline = time.monotonic() + budget.time_limit
    seen = set()
    counters = {"nodes": 0}

    def fingerprint(slot):
        board = frozenset(t.id for t in tiles if t.zone == "board")
        cnt = {}
        for s in slot:
            cnt[s.type] = cnt.get(s.type, 0) + 1
        return (board, tuple(sorted(cnt.items())))

    def dfs(slot):
        if all(t.zone == "gone" for t in tiles):
            return []
        counters["nodes"] += 1
        if counters["nodes"] > budget.max_nodes or time.monotonic() > deadline:
            raise _BudgetOut
        fp = fingerprint(slot)
        if fp in seen:
            return None
        seen.add(fp)
        refresh_cover(tiles)
        cnt = {}
        for s in slot:
            cnt[s.type] = cnt.get(s.type, 0) + 1

        def rank(t):
            # 启发式:先点槽内已凑 2 张的(立即消),其次 1 张的,最后新图案
            c = cnt.get(t.type, 0)
            return 0 if c == 2 else (1 if c == 1 else 2)

        cands = sorted((t for t in tiles if t.zone == "board" and t.clickable),
                       key=rank)
        for t in cands:
            if would_lose(slot, t):
                continue                       # 这张点了立即输,剪掉
            zones_before = {x.id: x.zone for x in tiles}
            slot_before = [x.id for x in slot]
            t.zone = "slot"
            for e in _insert(slot, t):
                e.zone = "gone"
            sub = dfs(slot)
            if sub is not None:
                return [t.id] + sub
            for x in tiles:                    # 回退:恢复快照再试下一张
                x.zone = zones_before[x.id]
            slot[:] = [index[i] for i in slot_before]
        return None

    try:
        return dfs(start_slot)
    except _BudgetOut:
        return None
