"""牌数据结构、关卡参数与骨架生成(设计文档 §4.4 / §5.2 模块 M1)。

骨架(每张牌的位置/层/区)与图案分布(type)是两件独立的事——这正是原版
架构:服务端下发骨架 JSON + map_seed 随机图案(设计文档 §3.1)。本项目用双
seed 复刻:skeleton_seed 定骨架形态(关卡内固定),pattern_seed 定图案分布
(每局随机,deal_random 传入)。

所有随机数都走 random.Random(seed) 独立实例,不用全局 random——同 seed 必出
同结果,测试可复现、多实例互不干扰。
"""
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

# 关卡参数文件:项目根下 game/data/levels.json
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "levels.json"

# 牌的去向流转:场上 → 槽 →(移出区)→ 已消除
ZONES = ("board", "slot", "out", "gone")

# 每张牌占 2×2 逻辑格:整数格上 |Δrol|<2 且 |Δrow|<2 即两牌矩形重叠
TILE_SPAN = 2

# 拒绝采样上限:一张牌试这么多次还放不下就报错(关卡参数过于拥挤),不静默
MAX_PLACE_TRIES = 200

# 倒生长的摞放偏好:每张新牌有此概率摞在已放好(更高层)牌的 ±1 邻域,
# 其余自由铺(纺锤塔的"下宽"就是这些自由牌扩张出来的)
STACK_BIAS = 0.75


class LevelError(ValueError):
    """关卡参数读不了/结构不对/数字对不上。报错一定带具体数字与字段。"""


@dataclass
class Tile:
    """一张牌(字段即契约 §5.2)。

    id:      A 区 "层-列-行"(照原版 id 格式),B 区 "B摞号-序号"
    type:    图案 id,0 = 还没发图案
    rol/row: 格坐标(整数即可半格错位;牌占 rol..rol+2 × row..row+2)
    layer:   层号,1 = 最底层,越大越靠上
    mold:    1 = A 区网格堆叠,2 = B 区盲盒摞
    zone:    board 场上 / slot 槽内 / out 移出区 / gone 已消除
    """

    id: str
    rol: int = 0
    row: int = 0
    layer: int = 1
    type: int = 0
    mold: int = 1
    zone: str = "board"

    def as_dict(self):
        """转普通 dict(快照/调试用)。"""
        return asdict(self)


# ---------------------------------------------------------------- 关卡参数

def load_levels(path=None):
    """读 data/levels.json 并做全部硬校验,返回 {关号字符串: 关参数 dict}。

    校验失败一律 LevelError 并带"哪个关、哪个字段、两边差多少"——关卡数据
    是整个游戏的地基,错一处后面全歪,绝不让它带病过闸。
    """
    p = Path(path) if path is not None else DATA_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LevelError(f"关卡文件读不了:{p}({exc})") from exc
    except json.JSONDecodeError as exc:
        raise LevelError(f"关卡文件不是合法 JSON:{p}({exc})") from exc
    if not isinstance(raw, dict) or not raw:
        raise LevelError(f"关卡文件顶层必须是非空对象:{p}")
    for lid, params in raw.items():
        _check_level(lid, params)
    return raw


def _check_level(lid, params):
    """校验单个关卡的参数:类型、范围、跨字段一致性。"""
    where = f"关 {lid}"
    if not isinstance(params, dict):
        raise LevelError(f"{where}:参数必须是对象,拿到 {type(params).__name__}")
    for key in ("name", "block_type_data", "skeleton_seed", "zone_a"):
        if key not in params:
            raise LevelError(f"{where}:缺字段 {key!r}")
    # 图案组数表:{"图案id": 组数};图案 id 是数字字符串、组数是正整数
    btd = params["block_type_data"]
    if not isinstance(btd, dict) or not btd:
        raise LevelError(f"{where}:block_type_data 必须是非空对象")
    groups_total = 0
    for tid, groups in btd.items():
        if not isinstance(tid, str) or not tid.isdigit():
            raise LevelError(f"{where}:图案 id 必须是数字字符串,拿到 {tid!r}")
        if not isinstance(groups, int) or isinstance(groups, bool) or groups < 1:
            raise LevelError(f"{where}:图案 {tid} 的组数必须是正整数,拿到 {groups!r}")
        groups_total += groups
    if not isinstance(params["skeleton_seed"], int) or isinstance(params["skeleton_seed"], bool):
        raise LevelError(f"{where}:skeleton_seed 必须是整数")
    # A 区网格与层曲线
    za = params["zone_a"]
    if not isinstance(za, dict):
        raise LevelError(f"{where}:zone_a 必须是对象")
    for key in ("cols", "rows", "layers", "total", "peak_layer", "peak_count", "edge"):
        if key not in za:
            raise LevelError(f"{where}:zone_a 缺字段 {key!r}")
        v = za[key]
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise LevelError(f"{where}:zone_a.{key} 必须是正整数,拿到 {v!r}")
    if za["peak_layer"] > za["layers"]:
        raise LevelError(f"{where}:peak_layer({za['peak_layer']}) 超出层数({za['layers']})")
    if za["peak_count"] < za["edge"]:
        raise LevelError(
            f"{where}:peak_count({za['peak_count']}) 不应小于 edge({za['edge']})"
        )
    # B 区盲盒摞(可选)
    zb = params.get("zone_b")
    b_total = 0
    if zb is not None:
        if not isinstance(zb, dict):
            raise LevelError(f"{where}:zone_b 必须是对象或 null")
        for key in ("stacks", "per_stack", "rol", "row"):
            if key not in zb:
                raise LevelError(f"{where}:zone_b 缺字段 {key!r}")
        if not isinstance(zb["stacks"], int) or isinstance(zb["stacks"], bool) or zb["stacks"] < 1:
            raise LevelError(f"{where}:zone_b.stacks 必须是正整数")
        if not isinstance(zb["per_stack"], int) or isinstance(zb["per_stack"], bool) or zb["per_stack"] < 1:
            raise LevelError(f"{where}:zone_b.per_stack 必须是正整数")
        if not isinstance(zb["rol"], list) or len(zb["rol"]) != zb["stacks"]:
            raise LevelError(f"{where}:zone_b.rol 数组长度必须等于 stacks({zb['stacks']})")
        for r in zb["rol"]:
            if not isinstance(r, int) or not (0 <= r <= za["cols"] - TILE_SPAN):
                raise LevelError(
                    f"{where}:zone_b.rol 元素 {r!r} 越界 [0, {za['cols'] - TILE_SPAN}]"
                )
        if not isinstance(zb["row"], int) or zb["row"] < 0:
            raise LevelError(f"{where}:zone_b.row 必须是非负整数")
        b_total = zb["stacks"] * zb["per_stack"]
    # 一致性:图案总张数(组数×3)必须恰好等于骨架牌数,否则发牌会缺牌/多牌
    from_deal = groups_total * 3
    from_skeleton = za["total"] + b_total
    if from_deal != from_skeleton:
        raise LevelError(
            f"{where}:图案 {groups_total} 组×3={from_deal} 张,与骨架牌数 "
            f"(zone_a {za['total']} + zone_b {b_total} = {from_skeleton})对不上"
        )


# ---------------------------------------------------------------- 层曲线

def _make_layer_counts(za):
    """把 zone_a 的纺锤参数变成每层张数列表(下标 0 = 第 1 层)。

    线性插值:两端 edge、peak_layer 处 peak_count;round 的零头与 total 有差
    时均摊——补牌往峰两侧加(峰顶不动,保峰形)、扣牌从离峰最远的层扣(每层
    保底 1 张)。参数差太远硬凑不出时直接报错,不掰出怪形状。
    """
    n, total = za["layers"], za["total"]
    pk_l, pk_c, edge = za["peak_layer"], za["peak_count"], za["edge"]
    counts = []
    for k in range(1, n + 1):
        if k <= pk_l:
            c = edge + (pk_c - edge) * (k - 1) / max(pk_l - 1, 1)
        else:
            c = edge + (pk_c - edge) * (n - k) / max(n - pk_l, 1)
        counts.append(max(1, round(c)))
    diff = total - sum(counts)
    if diff > 0:
        around = sorted(
            (i for i in range(n) if i != pk_l - 1),
            key=lambda i: (abs(i - (pk_l - 1)), i),
        )
        for j in range(diff):
            counts[around[j % len(around)]] += 1
    while diff < 0:
        far = sorted(range(n), key=lambda i: (-abs(i - (pk_l - 1)), i))
        for i in far:
            if diff == 0:
                break
            if counts[i] > 1:
                counts[i] -= 1
                diff += 1
        if diff < 0:
            raise LevelError(
                f"层曲线凑不出 total={total}:每层已保底 1 张仍差 {-diff} 张,调参数"
            )
    if sum(counts) != total:
        raise LevelError(f"层曲线内部不变量破坏:和 {sum(counts)} ≠ total={total}")
    if max(counts) > pk_c:
        raise LevelError(
            f"层曲线峰值 {max(counts)} 超过 peak_count={pk_c}:参数自相矛盾"
        )
    return counts


# ---------------------------------------------------------------- 骨架生成

def _overlap(rol_a, row_a, rol_b, row_b):
    """两牌 AABB 是否重叠:整数格上 |Δrol|<2 且 |Δrow|<2(各占 2×2 格)。"""
    return abs(rol_a - rol_b) < TILE_SPAN and abs(row_a - row_b) < TILE_SPAN


def make_skeleton(params, skeleton_seed):
    """按关卡参数生成骨架牌列表(只定位置/层/区,type 全 0)。

    倒生长:从最顶层(牌最少)开始往底层铺。每张新牌以 STACK_BIAS 概率摞在
    已放好(更高层)牌的 ±1 邻域——必然与它重叠,纸牌塔的堆叠感来源;剩下
    自由铺,纺锤塔"下宽上窄"就靠这些自由牌扩张出来。
    为什么不从底往上生长:原版 layerNum 是遮挡渲染的 z 序、不是物理支撑高度
    (§3.1 抓包的纺锤地图含跨层悬空),"中间层比下层宽"的纺锤从下往上生成时
    上层放不进下层的 ±1 邻域(batch 1 实测踩坑,见设计文档 §4.4 变更记录)。
    B 区:每摞同 (rol,row)、从底到顶 layer 1..per_stack。
    返回按 layer 升序(A 区在前、B 区在后):渲染层按序画,后画的盖先画的,
    遮挡自然正确。
    """
    rng = random.Random(skeleton_seed)
    za = params["zone_a"]
    counts = _make_layer_counts(za)
    cols, rows = za["cols"], za["rows"]
    placed = []      # 已放好的更高层牌(顶层先放,越放越低)
    tiles_a = []
    for li in range(len(counts), 0, -1):          # 顶层 → 底层
        cnt = counts[li - 1]
        layer_tiles = []
        for _ in range(cnt):
            for _try in range(MAX_PLACE_TRIES):
                if placed and rng.random() < STACK_BIAS:
                    base = placed[rng.randrange(len(placed))]
                    rol = base.rol + rng.randint(-1, 1)
                    row = base.row + rng.randint(-1, 1)
                    if not (0 <= rol <= cols - TILE_SPAN and 0 <= row <= rows - TILE_SPAN):
                        continue
                else:
                    rol = rng.randrange(cols - TILE_SPAN + 1)
                    row = rng.randrange(rows - TILE_SPAN + 1)
                # 同层两两不重叠(原版网格摆放,同层不互相压)
                if any(_overlap(rol, row, t.rol, t.row) for t in layer_tiles):
                    continue
                layer_tiles.append(Tile(id=f"{li}-{rol}-{row}", rol=rol, row=row,
                                        layer=li, type=0, mold=1, zone="board"))
                break
            else:
                raise LevelError(
                    f"骨架生成卡住:第 {li} 层第 {len(layer_tiles) + 1}/{cnt} 张牌 "
                    f"{MAX_PLACE_TRIES} 次采样未落位(grid {cols}×{rows} 太挤或层张数过多)"
                )
        tiles_a.extend(layer_tiles)
        placed.extend(layer_tiles)
    tiles_a.sort(key=lambda t: t.layer)           # 倒生长收集 → 按 layer 升序输出
    tiles = list(tiles_a)
    zb = params.get("zone_b")
    if zb:
        for s in range(1, zb["stacks"] + 1):
            rol = zb["rol"][s - 1]
            for k in range(1, zb["per_stack"] + 1):
                tiles.append(Tile(id=f"B{s}-{k}", rol=rol, row=zb["row"],
                                  layer=k, type=0, mold=2, zone="board"))
    return tiles


# ---------------------------------------------------------------- 图案分配

def deal_random(tiles, block_type_data, pattern_seed=None):
    """原味发牌(原版行为,设计文档 §3.1):每种图案 组数×3 张 → Fisher-Yates
    全局洗牌 → 按骨架顺序依次填 type。pattern_seed=None 每局真随机;传死值
    完全可复现。张数对不上直接 ValueError,不静默截断。
    """
    rng = random.Random() if pattern_seed is None else random.Random(pattern_seed)
    bag = []
    for tid, groups in block_type_data.items():
        bag.extend([int(tid)] * (groups * 3))
    if len(bag) != len(tiles):
        raise ValueError(
            f"发牌张数对不上:图案 {len(bag) // 3} 组×3={len(bag)} 张,"
            f"骨架有 {len(tiles)} 张"
        )
    rng.shuffle(bag)
    for tile, tid in zip(tiles, bag):
        tile.type = tid
