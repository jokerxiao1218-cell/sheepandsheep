"""batch 5 测试:自绘素材与中文字体链(设计文档 §6.5-20/22)。

SDL_VIDEODRIVER=dummy 必须在 import pygame 之前设好(§3.3 实测结论)。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game import assets  # noqa: E402


def setup_module():
    pygame.init()


def test_font_health():
    """§6.5-22:中文字体自检——宽度必须接近字号(默认字体是破碎占位符)。"""
    width = assets.check_font_health(32)
    assert width >= 25


def test_cn_font_renders_wide():
    f = assets.cn_font(24)
    w_cjk, _ = f.size("羊了个羊")
    # 4 个 24 号汉字宽约 85(站酷快乐体略窄于 Noto);默认字体的破碎占位符
    # 只有约 30——两边差近 3 倍。阈值取 0.8×86 留字体固有窄度,仍远高于占位符
    assert w_cjk >= 4 * 24 * 0.8


def test_emoji_font_renders_ink():
    """15 种图案的 emoji 在 Noto Emoji 单色字体里全部有真实墨水(不是空/豆腐)。"""
    for type_id, (emoji, color) in assets.FACES.items():
        surf, _ = assets.emoji_font(48).render(emoji, fgcolor=(*color, 255))
        w, h = surf.get_size()
        ink = sum(1 for x in range(0, w, 2) for y in range(0, h, 2)
                  if surf.get_at((x, y))[3] > 40)
        assert ink >= 8, f"图案 {type_id}({emoji}) emoji 无墨水:字体覆盖缺失"


def test_tile_face_pixels():
    """§6.5-20:15 种牌面全部可画:白卡面 + emoji 彩色墨水 + 底部淡色条。"""
    for type_id, (emoji, color) in assets.FACES.items():
        face = assets.tile_face(type_id, 72)
        assert face.get_size() == (72, 72)
        r, g, b, a = face.get_at((8, 8))          # 圆角内、图案外的卡面
        assert (r, g, b) == (255, 253, 248) and a == 255
        # emoji 真画出来了:图案区有非卡面白的墨水像素
        ink = sum(1 for x in range(14, 58, 2) for y in range(12, 48, 2)
                  if face.get_at((x, y))[:3] != (255, 253, 248))
        assert ink >= 8, f"图案 {type_id}({emoji}) 牌面无墨水"
        # 底部色条:图案专属色的淡版,和卡面白可区分
        assert face.get_at((36, 68))[:3] != (255, 253, 248)


def test_tile_face_cache_identity():
    assert assets.tile_face(3, 72) is assets.tile_face(3, 72)


def test_dim_face_is_darker():
    bright = assets.tile_face(1, 72).get_at((9, 9))
    dim = assets.dim_face(1, 72).get_at((9, 9))
    assert sum(dim[:3]) < sum(bright[:3])       # 暗纱真的压暗了


def test_button_states():
    on = assets.button("撤销", 72, 32, True)
    off = assets.button("撤销", 72, 32, False)
    assert on.get_size() == off.get_size() == (72, 32)
    on_max = max(max(on.get_at((x, 16))[:3]) for x in range(4, 68, 2))
    off_max = max(max(off.get_at((x, 16))[:3]) for x in range(4, 68, 2))
    # 中心横行扫过去:可用态字色(≈240)必须明显亮于禁用态字色(≈122)
    assert on_max > off_max + 50
