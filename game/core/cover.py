"""遮挡判定(设计文档 §3.1/§5.2 模块 M2)。

A 区:与任何更高层的牌发生 AABB 矩形重叠(哪怕只压住一小角)即被压、不可点
——抓包确证的口径。B 区:每摞只有最高层可点(原版盲盒摞只露顶牌)。
视觉三态:bright 无覆盖 / dim 被压灰显 / hidden 被 ≥2 个不同层覆盖(不渲染,
原版 20 多层的塔里整段被埋的牌就是这种)。

每次动作后全量重算(不做增量关系网):264 张牌 O(n²)≈7 万次整数比较毫秒级;
增量维护正是 yulegeyu 踩过的坑(撤回时漏了重绑覆盖关系),不做(§3.2)。
"""
from .tiles import TILE_SPAN

BRIGHT, DIM, HIDDEN = "bright", "dim", "hidden"


def covered(a, b):
    """两牌 AABB 是否重叠:整数格上 |Δrol|<2 且 |Δrow|<2(各占 2×2 格)。"""
    return abs(a.rol - b.rol) < TILE_SPAN and abs(a.row - b.row) < TILE_SPAN


def _stack_of(tile):
    """B 区牌的摞号:"B2-7" → "B2"。"""
    return tile.id.split("-")[0]


def refresh_cover(tiles):
    """全量重算每张场上(zone==board)牌的 clickable 与 visible,原地写回。

    A 区用空间哈希(每张牌注册到它占的 4 个格,查询只看共享格里的更高层
    牌)把"找更高层的重叠牌"从 O(n²) 降到 O(n)——264 张牌 22 层的塔,
    逆向构造/求解器一步一算也不卡。B 区仍在同摞内逐张比(每摞就 11 张)。
    等价性:AABB 重叠(|Δrol|<2 且 |Δrow|<2)⟺ 两张 2×2 牌存在共享格。
    """
    board = [t for t in tiles if t.zone == "board"]
    grid = {}          # (列,行)格 → 占这格的 A 区牌
    stacks = {}        # B 摞号 → 摞内牌
    for t in board:
        if t.mold == 1:
            for cell in ((t.rol, t.row), (t.rol + 1, t.row),
                         (t.rol, t.row + 1), (t.rol + 1, t.row + 1)):
                grid.setdefault(cell, []).append(t)
        else:
            stacks.setdefault(_stack_of(t), []).append(t)
    for t in board:
        if t.mold == 1:
            overlays = set()
            for cell in ((t.rol, t.row), (t.rol + 1, t.row),
                         (t.rol, t.row + 1), (t.rol + 1, t.row + 1)):
                for o in grid.get(cell, ()):
                    if o.layer > t.layer:
                        overlays.add(o)      # set 按身份去重(同一张牌占多个共享格)
        else:
            overlays = [o for o in stacks[_stack_of(t)] if o.layer > t.layer]
        t.clickable = not overlays
        n_layers = len({o.layer for o in overlays})
        t.visible = BRIGHT if n_layers == 0 else (DIM if n_layers == 1 else HIDDEN)


def pick(tiles, gx, gy):
    """格坐标 (gx,gy) 命中的场上牌里 layer 最高的一张(上层压住时点上层)。

    返回 None = 没点中。注意返回的牌未必可点:它可能被"不经过此点的更高层
    牌"压住一小角——那是暗牌,点它等于没反应(Game.click 会拒绝)。
    B 区同摞 11 张完全重合,命中取 layer 最高=摞顶,行为与"只有摞顶可点"一致。
    """
    best = None
    for t in tiles:
        if t.zone != "board":
            continue
        if t.rol <= gx < t.rol + TILE_SPAN and t.row <= gy < t.row + TILE_SPAN:
            if best is None or t.layer > best.layer:
                best = t
    return best
