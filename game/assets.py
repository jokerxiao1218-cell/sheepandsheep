"""自绘牌面/按钮与中文字体链(设计文档 §4.2 / §5.2 模块 M7)。

零外部素材红线:牌面 = 圆角矩形底色 + 单汉字符号(15 种图案 = 15 个
"底色+符号"组合),全部运行时 pygame 画,按 (type, 尺寸) 缓存。

中文字体是 pygame 的最大坑(§3.3 本机实测):默认字体渲染中文是破碎
占位符(宽只有字号一半不到);SysFont 名字必须带 sc 后缀('notosanscjksc',
不带后缀匹配不到);最可靠是路径直载 NotoSansCJK.ttc。check_font_health()
在启动时渲染一个字断言宽度,防静默回退到不支持中文的字体。
"""
import pygame

# 字体链:先路径直载(最可靠),失败再走系统字体名匹配
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_SYS_FALLBACK = "notosanscjksc"

# 15 种图案:汉字符号 + 底色(取原版牌面"农作物/工具"意象,高区分度配色)
FACES = {
    1: ("玉", (196, 90, 34)),    # 玉米·橙
    2: ("草", (106, 168, 79)),    # 草·绿
    3: ("萝", (219, 88, 96)),     # 萝卜·红
    4: ("白", (158, 200, 185)),   # 白菜·青
    5: ("叉", (150, 100, 160)),   # 叉子·紫
    6: ("剪", (210, 150, 60)),    # 剪刀·土黄
    7: ("奶", (235, 200, 90)),   # 奶瓶·奶黄
    8: ("铃", (200, 120, 90)),   # 铃铛·棕
    9: ("火", (230, 120, 70)),    # 火柴·橘红
    10: ("胡", (170, 60, 120)),   # 胡萝卜·紫红
    11: ("毛", (238, 238, 238)),  # 羊毛·白
    12: ("帽", (120, 130, 180)),  # 草帽·蓝
    13: ("桶", (90, 140, 150)),   # 水桶·蓝灰
    14: ("锄", (130, 170, 100)),  # 锄头·草绿
    15: ("手", (180, 90, 110)),   # 手套·玫红
}

_font_cache = {}
_face_cache = {}
_dim_cache = {}
_button_cache = {}


def cn_font(size):
    """中文字体(按字号缓存):路径直载 → 系统字体名回退。"""
    if size not in _font_cache:
        try:
            _font_cache[size] = pygame.font.Font(FONT_PATH, size)
        except (FileNotFoundError, OSError):
            _font_cache[size] = pygame.font.SysFont(FONT_SYS_FALLBACK, size)
    return _font_cache[size]


def check_font_health(size=32):
    """启动自检:渲染一个中文汉字,宽度必须接近字号——破碎占位符实测只有
    字号一半不到。不健康直接 raise(带安装指引),绝不静默顶着方块字运行。"""
    width = cn_font(size).size("羊")[0]
    if width < size * 0.8:
        raise RuntimeError(
            f"中文字体不可用(渲染'羊'宽 {width}px < {size}*0.8):"
            f"请安装 Noto Sans CJK,如 Ubuntu: sudo apt install fonts-noto-cjk"
        )
    return width


def _glyph_color(bg):
    """底色亮则字黑、底色暗则字白,保证任何配色下符号可读。"""
    r, g, b = bg
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (40, 40, 44) if lum > 150 else (255, 255, 255)


def tile_face(type_id, px):
    """画一张牌面:圆角矩形底色 + 高光描边 + 中央汉字符号。按 (type,px) 缓存。"""
    key = (type_id, px)
    if key not in _face_cache:
        ch, color = FACES[type_id]
        face = pygame.Surface((px, px), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, px, px)
        pygame.draw.rect(face, (*color, 255), rect, border_radius=max(4, px // 9))
        pygame.draw.rect(face, (255, 255, 255, 70), rect,
                         width=max(2, px // 36), border_radius=max(4, px // 9))
        glyph = cn_font(int(px * 0.52)).render(ch, True, _glyph_color(color))
        face.blit(glyph, glyph.get_rect(center=rect.center))
        _face_cache[key] = face
    return _face_cache[key]


def dim_face(type_id, px):
    """被压住的暗牌(灰显不可点):正常牌面叠一层半透明暗纱。缓存。"""
    key = (type_id, px)
    if key not in _dim_cache:
        dimmed = tile_face(type_id, px).copy()
        shade = pygame.Surface((px, px), pygame.SRCALPHA)
        shade.fill((16, 18, 26, 132))
        dimmed.blit(shade, (0, 0))
        _dim_cache[key] = dimmed
    return _dim_cache[key]


def button(text, w, h, enabled=True, font_size=20):
    """自绘按钮面:可用亮底白字、禁用灰底灰字。缓存。"""
    key = (text, w, h, enabled, font_size)
    if key not in _button_cache:
        face = pygame.Surface((w, h), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, w, h)
        bg = (72, 86, 120, 255) if enabled else (52, 56, 66, 255)
        pygame.draw.rect(face, bg, rect, border_radius=max(6, h // 4))
        color = (240, 244, 250) if enabled else (108, 112, 122)
        glyph = cn_font(font_size).render(text, True, color)
        face.blit(glyph, glyph.get_rect(center=rect.center))
        _button_cache[key] = face
    return _button_cache[key]
