#!/usr/bin/env python
"""渲染截图工具(无头):给指定关/种子存一张 PNG,并统计非背景像素占比。

用途:开发调试与验收存档——dummy 下就能"看到"画面内容(像素统计兜底,
证明画面不是全黑/全空)。
用法:.venv/bin/python scripts/screenshot.py <level> [seed] [mode] [out.png]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game.ui import App, MenuScene, PlayScene  # noqa: E402

BG = (36, 40, 52)


def content_ratio(screen):
    """采样网格点的非背景像素占比(画面有效内容的粗度量)。"""
    total = hits = 0
    for x in range(0, screen.get_width(), 10):
        for y in range(0, screen.get_height(), 10):
            total += 1
            if screen.get_at((x, y))[:3] != BG:
                hits += 1
    return hits / total


def main():
    level = sys.argv[1] if len(sys.argv) > 1 else "2"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    mode = sys.argv[3] if len(sys.argv) > 3 else "classic"
    out = sys.argv[4] if len(sys.argv) > 4 else f"/tmp/sheep_L{level}_{mode}.png"

    app = App()
    app.step([])                                  # 菜单首帧
    menu_ratio = content_ratio(app.screen)
    app.scenes = [PlayScene(app, int(level), mode, pattern_seed=seed)]
    app.step([])                                  # 开局一帧
    play_ratio = content_ratio(app.screen)
    pygame.image.save(app.screen, out)
    print(f"第 {level} 关({mode},seed={seed})→ {out}")
    print(f"画面内容占比:菜单 {menu_ratio:.1%} / 开局 {play_ratio:.1%}"
          f"(全黑/全空≈0,正常牌堆应 >10%)")
    return 0 if play_ratio > 0.10 else 1


if __name__ == "__main__":
    sys.exit(main())
