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
    # 4 个 24 号汉字宽约 96;默认字体的破碎占位符只有约 30——两边差 3 倍
    assert w_cjk >= 4 * 24 * 0.9


def test_tile_face_pixels():
    """§6.5-20:15 种牌面全部可画,中心像素等于各自底色。"""
    for type_id, (ch, color) in assets.FACES.items():
        face = assets.tile_face(type_id, 72)
        assert face.get_size() == (72, 72)
        # 中心是汉字笔画,取左上角(9,9) 离圆角和描边都远,必是底色
        r, g, b, a = face.get_at((9, 9))
        assert (r, g, b) == color, f"图案 {type_id} 底色错:{(r, g, b)} != {color}"
        assert a == 255


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
