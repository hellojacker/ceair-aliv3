# -*- coding: utf-8 -*-
"""ceair 滑块求解器（阿里云验证码 v3 · PUZZLE）。

对外只暴露这层聚合 API；子模块各管一件事：

    config.py   站点配置 / 真机画像 / 映射常数（唯一"该改的地方"）
    env.py      iv8 浏览器环境画像（navigator、screen、window…）
    gap.py      缺口识别（生产路径 detect_gap、诊断路径 solve）
    bridge.py   iv8 netLog ↔ 真实 HTTP 的四步握手桥
    solve.py    一次完整求解的主流程
    cli.py      命令行：轮次控制 + 判决判定 + 产物落盘
    js/         注入 iv8 的原生补丁与页面钩子（纯字符串，无逻辑）
"""
from .bridge import Bridge
from .cli import _field, main
from .config import (
    HERE,
    IMG_DISPLAY_SCALE,
    MACHINE,
    MAPPING_A,
    MAPPING_B,
    PAGE_URL,
    PIECE_CANVAS_OFFSET,
    PREFIX,
    REGION,
    SCENE_ID,
    SDK_JS,
    SDK_PATH,
    SHELL_HTML,
    UA,
)
from .env import build_env
from .gap import detect_gap, inverse_mapping, solve as solve_gap
from .solve import solve_once

__all__ = [
    "Bridge",
    "build_env",
    "detect_gap",
    "inverse_mapping",
    "solve_gap",
    "solve_once",
    "main",
    "HERE", "PAGE_URL", "SCENE_ID", "PREFIX", "REGION", "UA", "MACHINE",
    "MAPPING_A", "MAPPING_B", "PIECE_CANVAS_OFFSET", "IMG_DISPLAY_SCALE",
    "SDK_PATH", "SDK_JS", "SHELL_HTML",
]
