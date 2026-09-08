"""batch 2 测试:遮挡判定(设计文档 §6.1-2/5、§6.3-16)。

全部用手工构造的小牌局(不走生成器),把遮挡规则一条条钉死:
AABB 公式、部分被压即不可点、三态可见、B 区摞顶规则、A/B 区互不干扰。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import pytest

from game.core.cover import BRIGHT, DIM, HIDDEN, covered, pick, refresh_cover
from game.core.tiles import Tile


def mk(tid, rol, row, layer, mold=1, zone="board"):
    """手工摆一张牌(测试不依赖生成器,规则用最小牌局钉死)。"""
    return Tile(id=tid, rol=rol, row=row, layer=layer, mold=mold, zone=zone)


@pytest.mark.parametrize("rol_a,row_a,rol_b,row_b,expect", [
    (1, 1, 1, 1, True),     # 完全重合
    (1, 1, 2, 1, True),     # 半格错位,压住一大半
    (1, 1, 1, 2, True),     # 竖向半格错位
    (1, 1, 3, 1, False),    # 横向恰好并排(差 2 格,不重叠)
    (1, 1, 1, 3, False),    # 纵向恰好并排
    (1, 1, 2, 3, False),    # 行差 2,横差 1 → 不重叠
    (1, 1, 0, 0, True),     # 反向半格错位
])
def test_covered_formula(rol_a, row_a, rol_b, row_b, expect):
    a = mk("a", rol_a, row_a, 1)
    b = mk("b", rol_b, row_b, 2)
    assert covered(a, b) is expect


def test_refresh_cover_three_states():
    """完全压住 + 两层压 = hidden,一层压 = dim,无压 = bright。"""
    low = mk("low", 1, 1, 1)          # 底层,被 2、3 两层压
    mid = mk("mid", 1, 1, 2)          # 中层,被 3 层压
    top = mk("top", 1, 1, 3)          # 顶层,明牌
    free = mk("free", 8, 8, 1)        # 独立明牌
    refresh_cover([low, mid, top, free])
    assert (top.visible, top.clickable) == (BRIGHT, True)
    assert (mid.visible, mid.clickable) == (DIM, False)
    assert (low.visible, low.clickable) == (HIDDEN, False)
    assert (free.visible, free.clickable) == (BRIGHT, True)


def test_partial_overlap_blocks():
    """§6.1-2:只被压住一小角(半格错位)也不可点。"""
    low = mk("low", 1, 1, 1)
    corner = mk("corner", 2, 1, 2)    # 横差 1:压住一半
    refresh_cover([low, corner])
    assert low.clickable is False
    assert low.visible == DIM


def test_gap_not_overlap():
    """差恰好 2 格 = 并排不压:下层照常可点。"""
    low = mk("low", 1, 1, 1)
    beside = mk("beside", 3, 1, 2)
    refresh_cover([low, beside])
    assert low.clickable is True and low.visible == BRIGHT


def test_zone_b_stack_rules():
    """§6.3-16:B 区只有摞顶可点;第二张 dim、更深处 hidden;另一摞独立。"""
    stack1 = [mk(f"B1-{k}", 5, 5, k, mold=2) for k in range(1, 12)]
    stack2 = [mk(f"B2-{k}", 9, 9, k, mold=2) for k in range(1, 12)]
    refresh_cover(stack1 + stack2)
    assert stack1[10].clickable is True and stack1[10].visible == BRIGHT  # B1-11 摞顶
    assert stack1[9].clickable is False and stack1[9].visible == DIM      # B1-10
    assert stack1[8].clickable is False and stack1[8].visible == HIDDEN  # B1-9
    assert stack2[10].clickable is True                                   # 另一摞不受影响


def test_zone_b_not_blocked_by_zone_a():
    """§6.1-6:B 区牌与 A 区牌即使位置重叠也互不压制。

    关键构造:B 摞只有 B1-1/B1-2 两张,再放一张 A 区高层牌(层 9)压同位置。
    B1-1 只被 B1-2(一个层)压 → dim;若 A 区高层参与判定,B1-1 会被两个层
    压成 hidden——断言 dim 即证明 A/B 区互不干扰。
    """
    b1 = mk("B1-1", 5, 5, 1, mold=2)
    b2 = mk("B1-2", 5, 5, 2, mold=2)
    a_low = mk("a", 5, 5, 1)           # A 区底层,同位置
    a_top = mk("b", 5, 5, 9)           # A 区高层(层 9 > B1-1 的层 1)
    refresh_cover([b1, b2, a_low, a_top])
    assert b2.clickable is True                 # B 摞顶
    assert b1.clickable is False                # 被同摞 B1-2 压
    assert b1.visible == DIM                    # 只算 B1-2 一层——A 区没参与
    assert a_top.clickable is True              # A 区内部:无更高层
    assert a_low.clickable is False             # A 区内部:被 a_top 压


def test_uncover_after_gone():
    """§6.1-5:压牌移走(消除)后,下层自动解锁。"""
    low = mk("low", 1, 1, 1)
    top = mk("top", 1, 1, 2)
    refresh_cover([low, top])
    assert low.clickable is False
    top.zone = "gone"
    refresh_cover([low, top])
    assert low.clickable is True and low.visible == BRIGHT


def test_pick_topmost_and_misses():
    """点击命中:取 layer 最高;只命中下层时选下层;空点返回 None。

    low(1,1) 与 top(2,1) 半格错位互相重叠:点 (1,1) 只在 low 里;
    点 (2,1) 两个都命中 → 取上层 top。
    """
    low = mk("low", 1, 1, 1)
    top = mk("top", 2, 1, 2)
    assert pick([low, top], 2, 1) is top         # 双双命中,选中上层
    assert pick([low, top], 1, 1) is low         # 只命中下层边角
    assert pick([low, top], 20, 20) is None      # 空点
    top.zone = "slot"
    assert pick([low, top], 2, 1) is low         # 进槽的牌不再被点中


def test_pick_zone_b_returns_stack_top():
    """B 区同摞 11 张完全重合:命中取最高层=摞顶。"""
    stack = [mk(f"B1-{k}", 5, 5, k, mold=2) for k in range(1, 12)]
    assert pick(stack, 6, 6) is stack[10]
