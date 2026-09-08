"""底部 7 槽位:聚集插入、三消、满判定(设计文档 §3.1/§5.2 模块 M3)。

聚集插入(原版反编译 addNewBlockNode):进槽的牌插到槽内最后一张同图案牌
后面,没有同图案则插槽尾——所以槽内同图案永远相邻,"三张同图案即消除"
在槽里表现为"连续三张相同"。第 3 张同图案进槽瞬间同步消除,不做延迟占位:
动画期间牌不占槽,与原版 getCrushBlockNum "正在消的不计占用"对玩家等价。

只动列表、不改 tile.zone——状态流转归 Game 统一管(§5.2 分工)。
"""
SLOT_SIZE = 7


def insert(slot, tile):
    """把牌聚集插进槽,返回本次消除的牌(通常空列表;凑满 3 张同图案时 3 张)。

    同图案在槽内永远 ≤2 张(第 3 张进来的瞬间就消了),这是消牌正确性的
    核心不变量,测试用随机序列钉死。
    """
    at = len(slot)
    for i in range(len(slot) - 1, -1, -1):
        if slot[i].type == tile.type:
            at = i + 1
            break
    slot.insert(at, tile)
    same = [t for t in slot if t.type == tile.type]
    if len(same) >= 3:
        for t in same:
            slot.remove(t)
        return same
    return []


def is_full(slot):
    """槽满 7 张(插入+同步三消之后才判——动画不占位)。"""
    return len(slot) >= SLOT_SIZE


def would_lose(slot, tile):
    """预判:把 tile 插进当前槽会不会直接输。

    槽 6 张时:tile 是已有 2 张图案的第 3 张 → 进槽瞬间消,不输;否则第 7
    张占满、判负。槽不满 6 张永远不输。
    """
    if len(slot) < SLOT_SIZE - 1:
        return False
    return len([t for t in slot if t.type == tile.type]) < 2
