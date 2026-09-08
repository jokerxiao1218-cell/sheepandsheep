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


def test_menu_click_starts_level2_solvable():
    app = App()
    rect, _, _ = app.scene().buttons[2]
    app.step([click(rect.center)])
    assert app.scene().game.mode == "solvable"


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


def test_level1_autoplay_end_to_end():
    """§6.6-23 后半:第一关全程像素点击自动化,必到结算画面(胜)。"""
    app = App()
    app.scenes = [PlayScene(app, 1, "classic", pattern_seed=3)]
    scene = app.scene()
    rng = random.Random(3)
    for _ in range(500):
        if not isinstance(app.scene(), PlayScene):
            break
        if scene.game.status != "playing":
            app.step([])                      # 等动画播完 → 结算覆盖层压栈
            continue
        ids = scene.game.clickable_ids()
        if not ids:
            break
        tile = scene.game._index[rng.choice(ids)]
        rect = scene.tile_rect(tile)
        app.step([click(rect.center)])
    assert isinstance(app.scene(), ResultScene)
    assert app.scene().status == "win"
    # 结算画面:点"回菜单"
    menu_btn = next(r for r, t, a in app.scene().buttons if a == "menu")
    app.step([click(menu_btn.center)])
    assert isinstance(app.scene(), MenuScene)


def test_escape_returns_to_menu():
    app = App()
    app.scenes = [PlayScene(app, 2, "classic", pattern_seed=1)]
    app.step([pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})])
    assert isinstance(app.scene(), MenuScene)
