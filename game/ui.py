"""渲染交互层(设计文档 §5.2 模块 M8):场景栈 + 鼠标交互 + 动画。

分层铁律:ui 只读 Game 状态画图、把鼠标点击换算成牌再转发给 Game——
游戏逻辑零 pygame 全在 core(§4.1)。

场景栈(State 模式 + 下推自动机,§3.3):菜单(底)/ 游戏 / 结算(覆盖层,
播完最后一组动画再压栈)。App.run() 是主循环,App.step() 供无头测试单帧
驱动(SDL_VIDEODRIVER=dummy,事件直接以参数传入,不用 event.post)。

布局(540×960 竖屏,原版手机比例,奶油底+白卡牌面):
  标题栏 y 0~40(左上角标题)
  A 区 格原点 y=44、格 36px、牌 72×72(牌占 2×2 格,列数按关卡居中)
  B 区 2 摞盲盒 摞顶 y=632、每张向下偏 6px(原版只露 6px 阴影条)
  移出区 y=776(3 格,原版临时区在槽上方)
  道具栏 移出区右侧(3 个 96×48 大按钮:移出/洗牌/撤销——放槽附近才显眼,
        2026-09-09 用户反馈"缺少道具功能"后从顶部小按钮搬来)
  槽 y=856(7 格,原版槽在最底)
  状态行 y=932(屏底,场上/槽数计数——放 A 区内会被牌堆盖住)
"""
import pygame

from . import assets
from .core.game import Game
from .core.tween import ease_out_quad, lerp

W, H = 540, 960
FPS = 60
CELL = 36                    # 逻辑格像素
TILE = CELL * 2              # 牌边长(占 2×2 格)
A_TOP = 44                   # A 区格原点 y(A 区 x 按关卡列数居中)
B_TOP = 632                  # B 区摞顶牌 y
OUT_Y = 776                  # 移出区牌 y
SLOT_Y = 856                 # 槽牌 y
ROW_PITCH = 76               # 槽/移出区每格横向间距

BG = (246, 240, 227)         # 奶油底(原版米色牌桌)
PANEL = (230, 221, 203)      # 移出区/槽面板
FG = (96, 86, 70)            # 正文深棕灰
TITLE = (74, 62, 44)         # 标题深棕

# 槽/移出区 7 格在 540 宽里整体居中的起点(全宽居中,不跟着关卡列数走)
SLOT_X0 = (W - (7 * ROW_PITCH - (ROW_PITCH - TILE))) // 2
# A 区列数 = 最大列号 + 2(牌占 2×2 格,与 core 的 TILE_SPAN 对齐)
TILE_SPAN_COLS = 2

PROPS = (("move_out", "移出"), ("shuffle", "洗牌"), ("undo", "撤销"))


def _center_x(cols):
    """A 区格原点 x:让 cols 列的网格在 540 宽里水平居中。"""
    return (W - cols * CELL) // 2


class Scene:
    """场景基类:统一 handle_events/update/draw 接口。"""

    def __init__(self, app):
        self.app = app

    def enter(self):
        pass

    def exit(self):
        pass

    def handle_events(self, events):
        pass

    def update(self, dt):
        pass

    def draw(self, screen):
        pass


class MenuScene(Scene):
    """主菜单:两关三种模式入口 + 玩法一句话。"""

    def __init__(self, app):
        super().__init__(app)
        self.buttons = [
            (pygame.Rect(90, 300, 360, 64), "第一关 · 新手(3 图案)", (1, "classic")),
            (pygame.Rect(90, 390, 360, 64), "第二关 · 原味(地狱难度)", (2, "classic")),
            (pygame.Rect(90, 480, 360, 64), "第二关 · 可解(保你有机会)", (2, "solvable")),
            (pygame.Rect(90, 600, 360, 64), "退出", None),
        ]

    def handle_events(self, events):
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for rect, _, payload in self.buttons:
                    if rect.collidepoint(e.pos):
                        if payload is None:
                            self.app.running = False
                        else:
                            level, mode = payload
                            self.app.scenes = [PlayScene(self.app, level, mode)]
                        return

    def draw(self, screen):
        screen.fill(BG)
        title = assets.cn_font(64).render("羊了个羊", True, (82, 62, 34))
        screen.blit(title, title.get_rect(center=(W // 2, 150)))
        sub = assets.cn_font(22).render("点三张同图案消除 · 清空全场过关 · 槽满即负",
                                         True, FG)
        screen.blit(sub, sub.get_rect(center=(W // 2, 230)))
        for rect, text, _ in self.buttons:
            screen.blit(assets.button(text, rect.w, rect.h, True, 24),
                       rect.topleft)


class PlayScene(Scene):
    """游戏场景:渲染一局 Game + 鼠标/键盘交互 + 牌动画。"""

    def __init__(self, app, level, mode, pattern_seed=None):
        super().__init__(app)
        self.game = Game(level, mode=mode, pattern_seed=pattern_seed)
        board_a = [t for t in self.game.tiles if t.mold == 1]
        self.cols = (max(t.rol for t in board_a) + TILE_SPAN_COLS) if board_a else 12
        self.b_size = max((t.layer for t in self.game.tiles if t.mold == 2),
                          default=0)
        self.anims = []            # 牌动画:fly 飞入槽 / fade 淡出消除
        self._finish_pending = False
        self._click_lock = 0.0     # 防连点锁:点牌后 0.15s 内忽略下一次牌点击(§3.3)
        # 道具栏:移出区右侧一排大按钮(96×48),挨着槽——原版道具也在底部
        # 牌区,顶部小按钮曾被用户当成"没有道具功能"
        self.buttons = [
            (pygame.Rect(236 + i * 102, 788, 96, 48), kind, label)
            for i, (kind, label) in enumerate(PROPS)
        ]

    # ------------------------------------------------------------ 几何换算

    def tile_rect(self, t):
        """一张牌当前的像素矩形(A 区/B 区/槽/移出区);已消的牌 None。"""
        if t.zone == "slot":
            i = [s.id for s in self.game.slot].index(t.id)
            return pygame.Rect(SLOT_X0 + i * ROW_PITCH, SLOT_Y, TILE, TILE)
        if t.zone == "out":
            i = [o.id for o in self.game.out_zone].index(t.id)
            return pygame.Rect(SLOT_X0 + i * ROW_PITCH, OUT_Y, TILE, TILE)
        if t.zone != "board":
            return None
        if t.mold == 2:            # B 区盲盒:同摞同 x,层号越小越靠下(偏 6px)
            return pygame.Rect(_center_x(self.cols) + t.rol * CELL,
                               B_TOP + (self.b_size - t.layer) * 6, TILE, TILE)
        return pygame.Rect(_center_x(self.cols) + t.rol * CELL,
                           A_TOP + t.row * CELL, TILE, TILE)

    # ------------------------------------------------------------ 交互

    def handle_events(self, events):
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self._click(e.pos)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.app.scenes = [MenuScene(self.app)]
                elif e.key == pygame.K_r:
                    self.app.scenes = [PlayScene(self.app, self.game.level_id,
                                                self.game.mode)]

    def _click(self, pos):
        g = self.game
        if g.status != "playing":
            return
        for rect, kind, _ in self.buttons:          # 1) 道具按钮(不受连点锁限制)
            if rect.collidepoint(pos):
                if g.use_prop(kind):
                    self._sync_anims()               # 道具改了牌的区属:失效动画清掉
                return
        hits = []                                   # 2) 牌:命中取 layer 最高
        for t in g.tiles:
            if t.zone not in ("board", "out"):
                continue
            r = self.tile_rect(t)
            if r and r.collidepoint(pos):
                hits.append((t, r))
        if not hits:
            return
        if self._click_lock > 0:                    # 动画还在播:吞掉连点(§3.3)
            return
        target, frm = max(hits, key=lambda p: p[0].layer)
        slot_rects = {t.id: self.tile_rect(t) for t in g.slot}
        # 飞行终点 = 聚集插入后的真实槽位(同图案最后一张的右一格,槽空则末位)。
        # 不能用点击后的 len(slot):它比真实落位至少偏右一格,还会越出槽区。
        same_idx = [i for i, s in enumerate(g.slot) if s.type == target.type]
        ins = (same_idx[-1] + 1) if same_idx else len(g.slot)
        to = pygame.Rect(SLOT_X0 + ins * ROW_PITCH, SLOT_Y, TILE, TILE)
        r = g.click(target.id)
        if not r["ok"]:
            return
        if r["eliminated"]:
            for gone in r["eliminated"]:
                if gone is target:
                    continue                        # 被点的第 3 张走"边飞边淡",别重影
                self.anims.append({"tile": gone, "kind": "fade", "t": 0.0,
                                   "dur": 0.22, "rect": slot_rects[gone.id]})
            self.anims.append({"tile": target, "kind": "fade", "t": 0.0,
                               "dur": 0.22, "rect": to, "fly": frm})
        else:
            self.anims.append({"tile": target, "kind": "fly", "t": 0.0,
                               "dur": 0.16, "from": frm, "to": to})
        self._click_lock = 0.15
        if g.status != "playing":
            self._finish_pending = True

    def _sync_anims(self):
        """道具改变牌的区属后,丢弃终点已失效的动画。

        撤销把牌退回场上/移出区、移出把槽头牌搬去移出区——这些牌若还有
        进行中的 fly 动画(终点是槽),动画与真实位置会同屏画两份。
        牌已不在 slot/gone 的动画一律作废。
        """
        self.anims = [a for a in self.anims if a["tile"].zone in ("slot", "gone")]

    # ------------------------------------------------------------ 帧驱动

    def update(self, dt):
        if self._click_lock > 0:
            self._click_lock = max(0.0, self._click_lock - dt)
        alive = []
        for a in self.anims:
            a["t"] += dt
            if a["t"] < a["dur"]:
                alive.append(a)
        self.anims = alive
        if self._finish_pending and not self.anims:
            self.app.scenes.append(ResultScene(self.app, self.game.status,
                                               self.game.level_id, self.game.mode))
            self._finish_pending = False

    def draw(self, screen):
        g = self.game
        anim_ids = {a["tile"].id for a in self.anims}
        screen.fill(BG)
        self._draw_hud(screen)
        self._draw_panels(screen)
        self._draw_board(screen, anim_ids)
        self._draw_zones(screen, anim_ids)
        self._draw_anims(screen)
        if self._finish_pending:                    # 动画收尾的一瞬压个结算幕
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 60))
            screen.blit(veil, (0, 0))

    def _draw_hud(self, screen):
        title = assets.cn_font(26).render("羊了个羊", True, TITLE)
        screen.blit(title, (12, 8))
        g = self.game
        label = {"1": "第一关", "2": "第二关"}[g.level_id]
        if g.mode == "solvable":
            label += "·可解"
        info = assets.cn_font(18).render(
            f"{label} · 场上 {sum(1 for t in g.tiles if t.zone == 'board')} 张 · "
            f"槽 {len(g.slot)}/7", True, FG)
        screen.blit(info, (12, 932))          # 屏底空带:A 区再满也盖不到计数
        for rect, kind, text in self.buttons:
            ok = g.status == "playing" and not g.prop_used[kind] and (
                kind != "move_out" or len(g.slot) >= 3) and (
                kind != "undo" or bool(g.history))
            screen.blit(assets.button(text, rect.w, rect.h, ok, 22), rect.topleft)

    def _draw_panels(self, screen):
        for y in (OUT_Y - 8, SLOT_Y - 8):
            pygame.draw.rect(screen, PANEL,
                             pygame.Rect(2, y, W - 4, TILE + 16),
                             border_radius=12)

    def _draw_board(self, screen, anim_ids):
        # B 区整摞直接画(按 layer 升序,顶牌最后画自然盖住下面的,只露
        # 6px 边——无视 hidden,A 区的"不渲染"规则不适用于摞的物理堆叠)
        b = sorted((t for t in self.game.tiles
                    if t.mold == 2 and t.zone == "board" and t.id not in anim_ids),
                   key=lambda t: t.layer)
        for t in b:
            screen.blit(assets.tile_face(t.type, TILE), self.tile_rect(t).topleft)
        # A 区:bright 正常 / dim 灰纱 / hidden 不渲染(§3.1 三态)
        for t in self.game.tiles:
            if (t.zone == "board" and t.mold == 1 and t.id not in anim_ids
                    and t.visible != "hidden"):
                face = assets.dim_face(t.type, TILE) if t.visible == "dim" \
                    else assets.tile_face(t.type, TILE)
                screen.blit(face, self.tile_rect(t).topleft)

    def _draw_zones(self, screen, anim_ids):
        for t in list(self.game.slot) + list(self.game.out_zone):
            if t.id not in anim_ids:
                rect = self.tile_rect(t)
                if rect:                      # 守卫:zone 异常的牌不渲染也不崩
                    screen.blit(assets.tile_face(t.type, TILE), rect.topleft)

    def _draw_anims(self, screen):
        for a in self.anims:
            k = ease_out_quad(min(a["t"] / a["dur"], 1.0))
            face = assets.tile_face(a["tile"].type, TILE)
            if a["kind"] == "fly":
                pos = (lerp(a["from"].x, a["to"].x, k), lerp(a["from"].y, a["to"].y, k))
                screen.blit(face, pos)
            else:
                fading = face.copy()
                fading.set_alpha(int(255 * (1 - k)))
                if "fly" in a:                      # 被点的第 3 张:边飞边淡
                    pos = (lerp(a["fly"].x, a["rect"].x, k),
                           lerp(a["fly"].y, a["rect"].y, k))
                else:
                    pos = a["rect"].topleft
                screen.blit(fading, pos)


class ResultScene(Scene):
    """结算覆盖层:通关/失败 + 再来一局/回菜单。"""

    def __init__(self, app, status, level_id, mode):
        super().__init__(app)
        self.status = status
        self.level_id = level_id
        self.mode = mode
        # 压栈瞬间屏幕上正是终局画面:定格为结算幕的底图。此后每帧重铺
        # 底图再叠一次半透明纱——画面稳定;不定格的话每帧往旧画面上再叠
        # 一层纱,亮度逐帧衰减,终局画面 1 帧后就被纱埋成纯色。
        self.base = app.screen.copy()
        self.buttons = [
            (pygame.Rect(90, 520, 360, 64), "再来一局", "retry"),
            (pygame.Rect(90, 620, 360, 64), "回菜单", "menu"),
        ]

    def handle_events(self, events):
        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for rect, _, action in self.buttons:
                    if rect.collidepoint(e.pos):
                        if action == "retry":
                            self.app.scenes = [PlayScene(self.app, self.level_id,
                                                        self.mode)]
                        else:
                            self.app.scenes = [MenuScene(self.app)]
                        return

    def draw(self, screen):
        screen.blit(self.base, (0, 0))               # 底图定格:先重铺再叠纱
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((12, 14, 20, 200))
        screen.blit(veil, (0, 0))
        if self.status == "win":
            big, small = "成功加入羊群!", "你把 264 张/36 张牌全清了"
        else:
            big, small = "失败了,槽满啦", "别灰心,原版通关率也只有 0.01%"
        title = assets.cn_font(56).render(big, True, (250, 250, 250))
        screen.blit(title, title.get_rect(center=(W // 2, 380)))
        sub = assets.cn_font(22).render(small, True, (224, 220, 210))
        screen.blit(sub, sub.get_rect(center=(W // 2, 450)))
        for rect, text, _ in self.buttons:
            screen.blit(assets.button(text, rect.w, rect.h, True, 24), rect.topleft)


class App:
    """主程序:场景栈 + 主循环。run() 真跑,step() 给无头测试单帧驱动。"""

    def __init__(self):
        pygame.init()
        assets.check_font_health()      # 中文字体自检:破碎占位符直接报错(§3.3)
        pygame.display.set_caption("羊了个羊 · Pygame 复刻")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.scenes = [MenuScene(self)]

    def scene(self):
        return self.scenes[-1]

    def run(self):
        """主循环:事件泵 = 每帧 event.get()(太久不泵系统会判死,§3.3)。"""
        while self.running:
            events = []
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                else:
                    events.append(e)
            dt = self.clock.tick(FPS) / 1000
            self.scene().handle_events(events)
            self.scene().update(dt)
            self.scene().draw(self.screen)
            pygame.display.flip()
        pygame.quit()

    def step(self, events, dt=1 / FPS):
        """单帧驱动(无头测试):事件直接传参,不用 event.post。"""
        self.scene().handle_events(events)
        self.scene().update(dt)
        self.scene().draw(self.screen)
        pygame.display.flip()
