# -*- coding: utf-8 -*-
"""东航 www.ceair.com 登录滑块（阿里云验证码 2.0 v3 · PUZZLE 拼图）· iv8 纯 Python 离线求解器

这个文件是**兼容门面**：实现已按职责拆到 solver/ 包（见 docs/architecture.md）。
保留它是因为既有用法与 tools/ 下的脚本都按 `import ceair_solver` / `python ceair_solver.py` 调用。

    python ceair_solver.py                 # 离线求解一次，输出 CaptchaVerifyParam
    python ceair_solver.py --rounds 3      # 连续求解 3 次（看稳定性）
    python ceair_solver.py --until-t001=6  # 判到 T001 为止，最多 6 轮

输出：
    captcha_param.json     {param, success, verifyCode, verifyResponse, plaintext, xPos, slidePos}
    captcha_success.json   除 param 外的全部细节（含 trace / initResponse / verifyRequest）
    captcha_netlog.json    网络桥逐条记录

设计要点（详见 docs/ceair_captcha_report.md）：
  1. 目标 JS 只在 iv8（C++ V8 + 浏览器环境）里执行，不依赖 Node/浏览器；
  2. 社区版 iv8 没有真实网络栈 → netLog + add_resource 做四步握手桥接真请求；
  3. SDK 动态下发的 FeiLin / pe.0XX.js / main.css 由 Python 抓源码后同 realm eval 注入，
     并按 `function(t){ t ? 失败 : 成功 }` 语义无参触发 load；
  4. iv8 无 layout 通道，但本 SDK 拖动几何不依赖 layout（实测与真机逐点一致），
     故不注入物理量补丁：xPos = 0.0035556·s² + 0.07628·s；
  5. 缺口识别：块边界 ↔ 背景强边缘对齐打分（纯 numpy，无 opencv）。
"""
import sys

from solver import (  # noqa: F401  —— 门面导出，tools/ 依赖这些名字
    Bridge,
    MAPPING_A,
    MAPPING_B,
    MACHINE,
    PAGE_URL,
    PIECE_CANVAS_OFFSET,
    IMG_DISPLAY_SCALE,
    PREFIX,
    REGION,
    SCENE_ID,
    SDK_JS,
    SDK_PATH,
    SHELL_HTML,
    UA,
    _field,
    build_env,
    detect_gap,
    inverse_mapping,
    main,
    solve_once,
)
from solver.js.drag import DRAG_JS  # noqa: F401
from solver.js.hooks import HOOKS_JS  # noqa: F401
from solver.js.init import INIT_JS  # noqa: F401
from solver.js.patches import PATCH_JS, PATCH_STREAMS  # noqa: F401
from solver.config import HERE  # noqa: F401

if __name__ == "__main__":
    sys.exit(main())
