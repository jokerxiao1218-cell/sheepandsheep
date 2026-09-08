"""batch 5 测试:场景栈与点击链路(设计文档 §6.5-20/21、§6.6-23 后半)。

无头测试全链路:SDL dummy → App 单帧 step() → 构造鼠标事件直接传参
(不 post)→ Game 状态真变化 → 场景真切换。ui 测的是"点击像素坐标真的
换算成正确的牌、按钮真的接上道具"——渲染像素断言在 test_assets。
跑法:cd ~/sheepandsheep && ./test.sh
"""
import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game.ui import App, MenuScene, PlayScene, ResultScene  # noqa: E402


def click(pos):
    """构造一次左键按下事件(PlayScene 用 DOWN 判点击)。"""
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1})


def test_app_boots_headless():
    """§6.5-20:dummy 下 set_mode(540,960) 正常。"""
    app = App()
    assert app.screen.get_size() == (540, 960)
    assert isinstance(app.scene(), MenuScene)


def test_menu_click_starts_level1():
    app = App()
    rect, _, _ = app.scene().buttons[0]
    app.step([click(rect.center)])
    assert isinstance(app.scene(), PlayScene)
    assert app.scene().game.level_id == "1"
    assert app.scene().game.mode == "classic"       # payload 两个分量都钉


def test_menu_click_starts_level2_solvable():
    app = App()
    rect, _, _ = app.scene().buttons[2]
    app.step([click(rect.center)])
    assert isinstance(app.scene(), PlayScene)
    assert app.scene().game.mode == "solvable"
    assert app.scene().game.level_id == "2"         # 别接错关


def test_menu_payloads_all_wired():
    """4 个按钮的 payload 整表钉死:手写数组改错一半,这里立刻红。"""
    app = App()
    assert [p for _, _, p in app.scene().buttons] == [
        (1, "classic"), (2, "classic"), (2, "solvable"), None,
    ]


def test_click_tile_moves_to_slot():
    """§6.5-21:事件注入点击 → 牌真进槽(像素坐标→牌的换算链路)。"""
    app = App()
    app.scenes = [PlayScene(app, 1, "classic", pattern_seed=3)]
    scene = app.scene()
    target = next(t for t in scene.game.board_tiles() if t.clickable)
    rect = scene.tile_rect(target)
    before = len(scene.game.slot)
    app.step([click(rect.center)])
    assert len(scene.game.slot) == before + 1
    assert target.zone == "slot"


def test_click_dim_tile_noop():
    """点暗牌:链路上被 core 拒绝,槽不涨。"""
    app = App()
    app.scenes = [PlayScene(app, 2, "classic", pattern_seed=0)]
    scene = app.scene()
    dim = next(t for t in scene.game.board_tiles()
               if t.mold == 1 and t.visible == "dim")
    before = len(scene.game.slot)
    app.step([click(scene.tile_rect(dim).center)])
    assert len(scene.game.slot) == before
    assert dim.zone == "board"


def test_prop_button_wired():
    """道具按钮点击真的调 use_prop:先点 3 张不同图案进槽,再点"移出"。"""
    app = App()
    app.scenes = [PlayScene(app, 2, "classic", pattern_seed=0)]
    scene = app.scene()
    picked_types = set()
    for t in scene.game.board_tiles():
        if t.clickable and t.type not in picked_types and len(scene.game.slot) < 3:
            scene.game.click(t.id)
            picked_types.add(t.type)
    assert len(scene.game.slot) == 3
    btn = next(r for r, kind, _ in scene.buttons if kind == "move_out")
    app.step([click(btn.center)])
    assert scene.game.prop_used["move_out"] is True
    assert len(scene.game.slot) == 0
    assert len(scene.game.out_zone) == 3


def autoplay_level1(app, scene, seed=3):
    """第一关全程像素点击自动化,直到结算画面压栈。

    点一次歇 10 帧(>0.15s 防连点锁、>0.16s 飞行动画):真人手速节奏,
    连点本来就该被 UI 吞掉(§3.3)。
    """
    rng = random.Random(seed)
    for _ in range(2000):
        if not isinstance(app.scene(), PlayScene):
            return
        if scene.game.status != "playing":
            app.step([])                      # 等动画播完 → 结算覆盖层压栈
            continue
        ids = scene.game.clickable_ids()
        if not ids:
            return
        tile = scene.game._index[rng.choice(ids)]
        app.step([click(scene.tile_rect(tile).center)])
        for _ in range(10):
            if not isinstance(app.scene(), PlayScene):
                return
            app.step([])


def test_level1_autoplay_end_to_end():
    """§6.6-23 后半:第一关全程像素点击自动化,必到结算画面(胜)。"""
    app = App()
    app.scenes = [PlayScene(app, 1, "classic", pattern_seed=3)]
    autoplay_level1(app, app.scene())
    assert isinstance(app.scene(), ResultScene)
    assert app.scene().status == "win"
    # 结算画面:点"回菜单"
    menu_btn = next(r for r, t, a in app.scene().buttons if a == "menu")
    app.step([click(menu_btn.center)])
    assert isinstance(app.scene(), MenuScene)


def test_result_scene_veil_stable():
    """结算幕底图定格:第 1 帧与 6 帧后画面一致(回归:曾每帧往旧画面上
    再叠一层纱,亮度逐帧衰减,终局画面 1 帧后就被埋成纯色)。"""
    app = App()
    app.scenes = [PlayScene(app, 1, "classic", pattern_seed=3)]
    autoplay_level1(app, app.scene())
    assert isinstance(app.scene(), ResultScene)
    p1 = app.screen.get_at((270, 500))[:3]     # 结算幕首帧:底图+单层纱
    for _ in range(6):
        app.step([])
    p2 = app.screen.get_at((270, 500))[:3]
    assert p1 == p2, f"结算画面逐帧在变({p1} → {p2}):底图没定格,纱在累积"


def test_out_zone_click_back_eliminate_renders():
    """移出区牌点回槽再被三消:整条像素链路渲染不崩
    (回归:out_zone 残留 zone=gone 的牌,_draw_zones 曾在淡出动画播完的
    第一帧对 gone 牌取 tile_rect().topleft 抛 AttributeError,正常玩法必踩)。"""
    app = App()
    app.scenes = [PlayScene(app, 1, "classic", pattern_seed=5)]
    scene = app.scene()
    g = scene.game
    by_type = {}
    for t in g.board_tiles():
        if t.clickable:
            by_type.setdefault(t.type, []).append(t)
    trio = next(v for v in by_type.values() if len(v) >= 3)[:3]
    x = next(t for t in g.board_tiles()
             if t.clickable and t.type != trio[0].type)

    def settle():
        for _ in range(10):                   # 消化连点锁与飞行动画
            app.step([])

    for t in (trio[0], trio[1], x):           # 槽 [T, T, X](明牌像素点击)
        app.step([click(scene.tile_rect(t).center)])
        settle()
    btn = next(r for r, kind, _ in scene.buttons if kind == "move_out")
    app.step([click(btn.center)])             # 移出:out_zone = [T, T, X]
    settle()
    for t in (trio[0], trio[1]):               # 像素点回移出区那 2 张 T
        app.step([click(scene.tile_rect(t).center)])
        settle()
    app.step([click(scene.tile_rect(trio[2]).center)])   # 第 3 张 T → 三消
    for _ in range(30):                       # 播完 0.22s 淡出动画后连画 30 帧
        app.step([])                          # (回归点就在动画过期那一帧)
    assert g.status == "playing"
    assert g.snapshot()["out"] == 1           # 计数如实:只剩那张异图案牌
    assert [o.id for o in g.out_zone] == [x.id]


def test_escape_returns_to_menu():
    app = App()
    app.scenes = [PlayScene(app, 2, "classic", pattern_seed=1)]
    app.step([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})])
    assert isinstance(app.scene(), MenuScene)
