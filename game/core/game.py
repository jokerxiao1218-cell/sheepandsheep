"""Game 门面——ui / solver / 走查脚本只认它(设计文档 §5.2 模块 M5)。

把 tiles(牌与生成)、cover(遮挡)、slot(槽位)、props(道具,batch 3 接入)
串成一局游戏。错误处理契约(§5.2):程序性错误(非法 id、对局结束后继续
操作、非法模式)直接 raise ValueError 带完整上下文;交互性拒绝(点被压的
暗牌)返回 ClickResult(ok=False)——UI 把它显示成"没反应",不是错误。
"""
from .cover import pick as _pick, refresh_cover
from .slot import is_full, insert as _slot_insert
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
        if mode != "classic":
            raise ValueError(f"模式暂只支持 classic(solvable 于 batch 4 接入),收到 {mode!r}")
        params = levels[key]
        self.level_id = key
        self.mode = mode
        self.tiles = make_skeleton(params, params["skeleton_seed"])
        deal_random(self.tiles, params["block_type_data"], pattern_seed)
        self.slot = []            # 槽内牌(聚集有序)
        self.out_zone = []        # 移出区(batch 3 道具用)
        self.history = []         # 撤销栈 [(tile_id, 来源来源区)],batch 3 用
        self.prop_used = {"move_out": False, "shuffle": False, "undo": False}
        self.status = STATUS_PLAYING
        self._index = {t.id: t for t in self.tiles}
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
