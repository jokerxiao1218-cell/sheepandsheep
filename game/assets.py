"""牌面/按钮绘制与中文字体链(设计文档 §4.2 / §5.2 模块 M7)。

牌面 = 白色圆角卡 + 彩色 emoji 图案(单色 emoji 字体按图案专属色染色)+
 底部淡色条,全部运行时 pygame 画,按 (type, 尺寸) 缓存。

字体素材(2026-09-09 起内置,用户反馈"字太丑去下载一点"后的变更):
- ZCOOLKuaiLe-Regular.ttf   站酷快乐体(OFL 开源)——UI 中文字体,圆润游戏感
- NotoEmoji-VF.ttf          Noto Emoji 单色可变版(OFL 开源)——牌面图案
两份 OFL 协议文本同目录。运行时不联网,字体随仓库走。
回退链:项目内置 → 系统 NotoSansCJK 路径 → SysFont('notosanscjksc')——
pygame 的中文坑(§3.3 本机实测):默认字体渲染中文是破碎占位符(宽只有
字号一半不到);SysFont 名字必须带 sc 后缀;最可靠是路径直载。
check_font_health() 启动时渲染"羊"断言宽度,防静默回退到不支持中文的字体。
"""
from pathlib import Path

import pygame
import pygame.freetype as ft

# 字体文件:项目内置(仓库内路径,相对本文件定位,不依赖 CWD)
_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_PATH = str(_DIR / "ZCOOLKuaiLe-Regular.ttf")
FONT_SYS_FALLBACK_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_SYS_FALLBACK = "notosanscjksc"
EMOJI_FONT_PATH = str(_DIR / "NotoEmoji-VF.ttf")

# 15 种图案:emoji 符号 + 专属色(取原版牌面"农作物/工具/天气"意象,
# 高区分度配色;单色 emoji 轮廓按此色染色,白卡上彩色图案 ≈ 原版卡通风)
FACES = {
    1: ("🌽", (214, 128, 32)),     # 玉米·金
    2: ("🌱", (92, 164, 66)),      # 苗·绿
    3: ("🥕", (222, 104, 44)),     # 胡萝卜·橙
    4: ("🥬", (66, 150, 100)),     # 白菜·青绿
    5: ("✂️", (98, 108, 128)),     # 剪刀·蓝灰
    6: ("🔔", (198, 138, 28)),     # 铃铛·金棕
    7: ("🔥", (222, 74, 52)),      # 火·红
    8: ("🧶", (186, 66, 118)),     # 毛线·玫红
    9: ("⏰", (72, 86, 112)),      # 闹钟·深蓝灰
    10: ("🧤", (156, 76, 58)),     # 手套·棕红
    11: ("🐑", (148, 128, 96)),    # 羊毛·米棕
    12: ("🌙", (74, 96, 170)),     # 月亮·蓝
    13: ("💧", (58, 126, 190)),    # 水·天蓝
    14: ("🪵", (140, 96, 58)),     # 木头·棕
    15: ("❄️", (100, 158, 190)),   # 雪·冰蓝
}

# 牌面基础色(奶油卡片风)
CARD_BG = (255, 253, 248)          # 卡面白
CARD_EDGE = (216, 208, 193)        # 卡缘描边
CARD_DIM_BG = (233, 231, 226)      # 暗牌卡面灰
CARD_DIM_EDGE = (204, 202, 196)
GLYPH_DIM = (152, 152, 150)        # 暗牌图案灰

_font_cache = {}
_emoji_cache = {}
_face_cache = {}
_dim_cache = {}
_button_cache = {}


def cn_font(size):
    """中文字体(按字号缓存):项目内置站酷快乐体 → 系统 Noto 路径 → SysFont。"""
    if size not in _font_cache:
        try:
            _font_cache[size] = pygame.font.Font(FONT_PATH, size)
        except (FileNotFoundError, OSError):
            try:
                _font_cache[size] = pygame.font.Font(FONT_SYS_FALLBACK_PATH, size)
            except (FileNotFoundError, OSError):
                _font_cache[size] = pygame.font.SysFont(FONT_SYS_FALLBACK, size)
    return _font_cache[size]


def emoji_font(size):
    """emoji 字体(freetype 单色渲染,按字号缓存)。"""
    if size not in _emoji_cache:
        _emoji_cache[size] = ft.Font(EMOJI_FONT_PATH, size=size)
    return _emoji_cache[size]


def check_font_health(size=32):
    """启动自检:渲染一个中文汉字,宽度必须接近字号——破碎占位符实测只有
    字号一半不到。不健康直接 raise(带指引),绝不静默顶着方块字运行。"""
    width = cn_font(size).size("羊")[0]
    if width < size * 0.7:
        raise RuntimeError(
            f"中文字体不可用(渲染'羊'宽 {width}px < {size}*0.7):"
            f"项目字体 {FONT_PATH} 缺失或损坏;回退系统字体需安装"
            f" Noto Sans CJK(Ubuntu: sudo apt install fonts-noto-cjk)"
        )
    return width


def _tint(color, k):
    """颜色向白色提亮(k=0 原色,k=1 纯白)——底部色条用淡版图案色。"""
    r, g, b = color
    return (int(r + (255 - r) * k), int(g + (255 - g) * k), int(b + (255 - b) * k))


def _make_face(type_id, px, dim):
    """画一张牌:白圆角卡 + 中央彩色 emoji + 底部淡色条;dim=True 画灰暗版。"""
    emoji, color = FACES[type_id]
    face = pygame.Surface((px, px), pygame.SRCALPHA)
    rect = pygame.Rect(0, 0, px, px)
    rad = max(4, px // 7)
    bar_h = max(5, px // 8)
    card_bg = CARD_DIM_BG if dim else CARD_BG
    edge = CARD_DIM_EDGE if dim else CARD_EDGE
    glyph_color = GLYPH_DIM if dim else color
    bar_color = _tint(GLYPH_DIM, 0.62) if dim else _tint(color, 0.68)
    pygame.draw.rect(face, (*card_bg, 255), rect, border_radius=rad)
    pygame.draw.rect(face, (*edge, 255), rect, width=max(2, px // 36),
                     border_radius=rad)
    bar = pygame.Rect(0, px - bar_h, px, bar_h)
    pygame.draw.rect(face, (*bar_color, 255), bar,
                     border_bottom_left_radius=rad,
                     border_bottom_right_radius=rad)
    glyph, _ = emoji_font(int(px * 0.62)).render(emoji, fgcolor=(*glyph_color, 255))
    area = pygame.Rect(0, 0, px, px - bar_h)          # 图案区:色条上方整体居中
    face.blit(glyph, glyph.get_rect(center=area.center))
    return face


def tile_face(type_id, px):
    """亮牌面(可点)。按 (type,px) 缓存。"""
    key = (type_id, px)
    if key not in _face_cache:
        _face_cache[key] = _make_face(type_id, px, dim=False)
    return _face_cache[key]


def dim_face(type_id, px):
    """被压住的暗牌(灰显不可点):灰卡 + 灰图案 + 灰色条。缓存。"""
    key = (type_id, px)
    if key not in _dim_cache:
        _dim_cache[key] = _make_face(type_id, px, dim=True)
    return _dim_cache[key]


def button(text, w, h, enabled=True, font_size=20):
    """自绘按钮面:可用 = 亮橙底白字、禁用 = 浅灰底灰字。缓存。"""
    key = (text, w, h, enabled, font_size)
    if key not in _button_cache:
        face = pygame.Surface((w, h), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, w, h)
        bg = (236, 122, 52, 255) if enabled else (190, 184, 174, 255)
        pygame.draw.rect(face, bg, rect, border_radius=max(6, h // 4))
        color = (255, 252, 246) if enabled else (140, 136, 128)
        glyph = cn_font(font_size).render(text, True, color)
        face.blit(glyph, glyph.get_rect(center=rect.center))
        _button_cache[key] = face
    return _button_cache[key]
