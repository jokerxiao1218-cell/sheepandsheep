"""Game 门面——ui / solver / 走查脚本只认它(设计文档 §5.2 模块 M5)。

把 tiles(牌与生成)、cover(遮挡)、slot(槽位)、props(道具,batch 3 接入)
串成一局游戏。错误处理契约(§5.2):程序性错误(非法 id、对局结束后继续
操作、非法模式)直接 raise ValueError 带完整上下文;交互性拒绝(点被压的
暗牌)返回 ClickResult(ok=False)——UI 把它显示成"没反应",不是错误。
"""
import random

from .cover import pick as _pick, refresh_cover
from .props import move_out as _move_out, shuffle_tiles, undo_pop
from .slot import is_full, insert as _slot_insert
from .solver import deal_solvable
from .tiles import deal_random, load_levels, make_skeleton

STATUS_PLAYING, STATUS_WIN, STATUS_LOSE = "playing", "win", "lose"


class Game:
    """一局游戏。构造即开局,seed 决定可复现性(§4.4 双 seed)。

    level_id:     关号(1 新手关 / 2 正式关)
    mode:         "classic" 原味随机发牌("solvable" 可解模式 batch 4 接入)
    pattern_seed: 图案分布种子,None=每局真随机;传死值=完全可复现
    """

    def __init__(self, level_id, mode="classic", pattern_seed=None):
        levels = load_levels()
        key = str(level_id)
        if key not in levels:
            raise ValueError(f"没有这一关:{level_id!r},现有 {sorted(levels)}")
        if mode not in ("classic", "solvable"):
            raise ValueError(f"模式只支持 classic/solvable,收到 {mode!r}")
        params = levels[key]
        self.level_id = key
        self.mode = mode
        self.tiles = make_skeleton(params, params["skeleton_seed"])
        self.solution = None          # solvable 模式存构造出的通关序列
        if mode == "classic":
            deal_random(self.tiles, params["block_type_data"], pattern_seed)
        else:
            seed = pattern_seed if pattern_seed is not None \
                else random.randrange(2 ** 31)
            self.solution = deal_solvable(self.tiles, params["block_type_data"], seed)
        self.slot = []            # 槽内牌(聚集有序)
        self.out_zone = []        # 移出区(batch 3 道具用)
        self.history = []         # 撤销栈 [(tile_id, 来源来源区)],batch 3 用
        self.prop_used = {"move_out": False, "shuffle": False, "undo": False}
        self.status = STATUS_PLAYING
        self._index = {t.id: t for t in self.tiles}
        # 洗牌道具的随机源:pattern_seed 传死值时同 seed 复现同洗牌,否则真随机
        self._rng = random.Random(pattern_seed)
        refresh_cover(self.tiles)

    # ---------------------------------------------------------------- 查询

    def board_tiles(self):
        """场上牌(渲染/求解用,只读视图)。"""
        return [t for t in self.tiles if t.zone == "board"]

    def clickable_ids(self):
        """当前可点牌 id 集合(求解器/走查脚本用)。"""
        return [t.id for t in self.tiles if t.zone == "board" and t.clickable]

    def snapshot(self):
        """关键统计(调试/显示用)。"""
        return {
            "level": self.level_id, "mode": self.mode, "status": self.status,
            "board": sum(1 for t in self.tiles if t.zone == "board"),
            "slot": len(self.slot),
            "out": len(self.out_zone),
            "gone": sum(1 for t in self.tiles if t.zone == "gone"),
            "props": dict(self.prop_used),
        }

    # ---------------------------------------------------------------- 操作

    def click(self, tile_id):
        """点牌:场上可点牌/移出区牌进槽,返回 ClickResult。

        ClickResult = {"ok": bool, "reason": str, "eliminated": list[Tile]}
        ok=False 的原因只有交互性拒绝:牌被压、牌不在可点区、没点中。
        """
        if self.status != STATUS_PLAYING:
            raise ValueError(f"对局已结束({self.status}),不能再点 {tile_id!r}")
        if tile_id not in self._index:
            raise ValueError(f"没有这张牌:{tile_id!r}")
        tile = self._index[tile_id]
        if tile.zone in ("slot", "gone"):
            return {"ok": False, "reason": f"牌 {tile_id} 已不在可点区",
                    "eliminated": []}
        if tile.zone == "board" and not tile.clickable:
            return {"ok": False, "reason": f"牌 {tile_id} 被压住,点不了",
                    "eliminated": []}
        source = tile.zone                       # "board" 或 "out"
        tile.zone = "slot"
        eliminated = _slot_insert(self.slot, tile)
        for t in eliminated:
            t.zone = "gone"
        if eliminated:
            self.history.clear()                 # 消除后不可撤(反编译口径,§3.1)
        else:
            self.history.append((tile_id, source))
        refresh_cover(self.tiles)
        if all(t.zone == "gone" for t in self.tiles):
            self.status = STATUS_WIN
        elif is_full(self.slot):
            self.status = STATUS_LOSE
        return {"ok": True, "reason": "", "eliminated": eliminated}

    def click_at(self, gx, gy):
        """格坐标点击:cover.pick 找命中牌再走 click。没点中返回 ok=False。"""
        t = _pick(self.tiles, gx, gy)
        if t is None:
            return {"ok": False, "reason": "没点中任何牌", "eliminated": []}
        return self.click(t.id)

    # ---------------------------------------------------------------- 道具

    def use_prop(self, kind):
        """用道具(每局各 1 次,原版口径 §3.1)。返回是否成功。

        交互性失败(槽不够 3 张、没有可撤的步、本局用过)返回 False——UI
        应把对应按钮置灰;程序性错误(不存在的道具名、对局已结束)raise。
        """
        if self.status != STATUS_PLAYING:
            raise ValueError(f"对局已结束({self.status}),不能用道具 {kind!r}")
        if kind not in self.prop_used:
            raise ValueError(f"没有这种道具:{kind!r},现有 {list(self.prop_used)}")
        if self.prop_used[kind]:
            return False
        if kind == "move_out":
            moved = _move_out(self.slot, self.out_zone, self.history)
            if moved is None:
                return False                       # 槽不足 3 张,不动道具次数
            for t in moved:
                t.zone = "out"
            self.prop_used[kind] = True
            return True
        if kind == "shuffle":
            shuffle_tiles(self.tiles, self._rng)
            self.prop_used[kind] = True
            return True
        # undo:撤销最后一张进槽的牌,退回来源(场上/移出区)
        step = undo_pop(self.history)
        if step is None:
            return False                           # 没有可撤的步
        tile_id, source = step
        tile = self._index[tile_id]
        self.slot.remove(tile)                     # 按对象身份移除(正是那张牌)
        tile.zone = source                          # "board" 或 "out"
        refresh_cover(self.tiles)                   # 回场上的牌重新判定遮挡
        self.prop_used[kind] = True
        return True
