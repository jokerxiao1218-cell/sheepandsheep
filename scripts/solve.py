#!/usr/bin/env python
"""关卡可解性求解工具(设计文档 §3.4,batch 4)。

对给定关号 + 图案种子构造一局,用回溯求解器回答"不用道具能否通关"。
可解 → 打印解的步数与序列;预算内没能证明 → 如实说明(NP-hard 不硬撑)。

用法:
  .venv/bin/python scripts/solve.py 2 12345            # 第二关,图案种子 12345
  .venv/bin/python scripts/solve.py 2 12345 --nodes 500000 --time 30
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from game.core.game import Game  # noqa: E402
from game.core.solver import SolveBudget, solve  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="羊了个羊可解性求解器")
    ap.add_argument("level", type=int, help="关号(1 或 2)")
    ap.add_argument("seed", nargs="?", type=int, default=0,
                    help="图案种子(默认 0;不同种子=不同图案分布)")
    ap.add_argument("--nodes", type=int, default=200_000, help="节点数预算")
    ap.add_argument("--time", type=float, default=10.0, help="时间预算(秒)")
    ap.add_argument("--show", type=int, default=20, help="展示解的前几步")
    args = ap.parse_args()

    g = Game(args.level, pattern_seed=args.seed)
    print(f"第 {args.level} 关 · 图案种子 {args.seed} · "
          f"{len(g.tiles)} 张牌 · 开局可点 {len(g.clickable_ids())} 张")
    seq = solve(g, SolveBudget(max_nodes=args.nodes, time_limit=args.time))
    if seq is None:
        print(f"预算({args.nodes} 节点 / {args.time}s)内未证明可解——"
              f"可能无解,也可能只是没搜到(三消可解性是 NP-hard)")
        return 1
    print(f"可解!共 {len(seq)} 步,前 {min(args.show, len(seq))} 步:")
    print(" ".join(seq[:args.show]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
