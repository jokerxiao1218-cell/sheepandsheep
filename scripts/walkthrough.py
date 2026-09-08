#!/usr/bin/env python
"""无头自动对局验收(设计文档 §6.6-23,batch 4 逻辑版)。

全部用真实引擎、真实规则、零 pygame,验收三件事:
1. 第一关经典模式:100 局随机瞎点全部必胜(3 种图案 7 槽的鸽巢原理);
2. 第二关经典模式:随机瞎点必输(原版"真随机地狱"口径的复现);
3. 第二关可解模式:逆向构造序列逐步回放,必胜(构造即证明)。
退出码 0 = 全部符合预期;1 = 有任何一项不符(打印坏在哪一步)。
跑法:cd ~/sheepandsheep && env -u PYTHONPATH .venv/bin/python scripts/walkthrough.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from game.core.game import Game  # noqa: E402


def play_random(g, seed):
    rng = random.Random(seed)
    while g.status == "playing":
        g.click(rng.choice(g.clickable_ids()))
    return g.status


def main():
    ok = True

    wins = sum(play_random(Game(1, pattern_seed=s), s) == "win"
               for s in range(100))
    print(f"[1] 第一关经典:随机 100 局胜 {wins}/100(预期 100——鸽巢必胜)")
    ok &= wins == 100

    status = play_random(Game(2, pattern_seed=0), 0)
    print(f"[2] 第二关经典:随机 1 局 status={status}(预期 lose——真随机地狱)")
    ok &= status == "lose"

    g = Game(2, mode="solvable", pattern_seed=2022)
    for i, tid in enumerate(g.solution):
        r = g.click(tid)
        if not r["ok"]:
            print(f"    构造序列在第 {i} 步点 {tid} 不可点:构造器有 bug")
            ok = False
            break
    else:
        print(f"[3] 第二关可解:构造序列 {len(g.solution)} 步回放 "
              f"status={g.status}(预期 win)")
        ok &= g.status == "win"

    print("walkthrough:", "全部通过" if ok else "有失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
