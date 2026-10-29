# -*- coding: utf-8 -*-
"""缺口识别 v2：用「块边界 ↔ 背景强边缘」对齐打分。

原理：拼图块与背景缺口形状逐像素一致；把块边界（掩膜外轮廓）沿 x 方向滑动，
背景在缺口边界处存在强边缘（缺口描边/明暗交界），得分最高的 x 即缺口位置。

本文件是诊断用门面：实现已并入 solver/gap.py（与生产路径 detect_gap 同源但不合并，
以免改变已标定的求解结果）。保留 `from gap2 import solve` / `python gap2.py` 两种用法。
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace',
                            line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))

from solver.gap import boundary, load, solve, sobel_mag  # noqa: E402,F401

if __name__ == '__main__':
    # 默认用最近一次求解落盘的图（ceair_solver.py 每轮覆盖写 back.png / shadow.png）
    b = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'back.png')
    p = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'shadow.png')
    print(solve(b, p))
