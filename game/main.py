"""入口:./run.sh(或 .venv/bin/python game/main.py)——一切从菜单开始。"""
import sys
from pathlib import Path

# 兼容两种跑法:python -m game.main 与 python game/main.py。后者 sys.path
# 里只有 game/ 这一层,不补仓库根目录就 import 不到 game 包(mota50 同款处理)
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.ui import App

if __name__ == "__main__":
    raise SystemExit(App().run())
