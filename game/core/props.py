"""三道具与撤销历史(设计文档 §3.1/§5.2 模块 M4)。

三个道具的效果全部按原版反编译口径实现(P1kaj1uu/Wechat-Sheep-And-Sheep):
- 移出 moveOutBlock:槽头顺序取前 3 张(玩家不能挑)进移出区;移出区的牌
  可再点回槽;使用移出会清空撤销历史;移出区有牌不算赢;
- 撤销 cancelOneStep:撤回最后一张进槽的牌,退回来源(场上原位/移出区);
  跨消除不可撤(消除时历史清空);每局免费 1 次;
- 洗牌 updateBlockArea:只重排场上未点牌的图案,位置/槽/移出区/已消全不动
  (带旋转动画是 UI 层的事)。

与 slot.py 同分工:本模块只动列表/字典,不改 tile.zone——状态流转归 Game。
"""
OUT_SIZE = 3      # 移出道具一次移几张(原版固定 3)


def move_out(slot, out_zone, history):
    """移出道具:槽头顺序取前 3 张进移出区,清空撤销历史。

    槽不足 3 张时什么都不动、返回 None(不部分移动——道具留给够 3 张再用)。
    成功返回移出的 3 张(顺序即原槽头顺序)。
    """
    if len(slot) < OUT_SIZE:
        return None
    moved = [slot.pop(0) for _ in range(OUT_SIZE)]
    out_zone.extend(moved)
    history.clear()          # 反编译口径:用移出会清空撤销历史
    return moved


def shuffle_tiles(tiles, rng):
    """洗牌道具:场上(zone==board)牌的图案重新随机分配,位置一律不动。

    槽内、移出区、已消除的牌不参与(反编译 updateBlockArea 只遍历棋盘牌堆
    区)。A+B 区一起洗:原版 B 区盲盒是否参与无确证(§3.4),盲盒看不见
    图案、行为无感知差异,统一处理(§4.6-5 设计决定)。
    """
    board = [t for t in tiles if t.zone == "board"]
    types = [t.type for t in board]
    rng.shuffle(types)
    for t, v in zip(board, types):
        t.type = v


def undo_pop(history):
    """弹撤销栈顶,返回 (tile_id, 来源区) 或 None(栈空=没有可撤的步)。"""
    return history.pop() if history else None
