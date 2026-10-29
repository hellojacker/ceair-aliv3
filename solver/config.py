# -*- coding: utf-8 -*-
"""站点配置、真机画像与几何映射常数。

这里集中所有"会随目标站/设备变的东西"。换站点、换画像、重标定映射，只改本文件；
求解流程（solve.py）与网络桥（bridge.py）不应出现任何硬编码常量。
"""
import io
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # solver/ -> 项目根

# ─────────────────────────── 目标站配置（东航） ───────────────────────────
PAGE_URL = "https://www.ceair.com/zh/cny/home"
SCENE_ID = "10hhki73"          # 站点 SceneId（global-login.bundle.js @146702）
PREFIX = "pxb8fg"              # 站点 prefix（/js/AliyunCaptchaConfig.js）
REGION = "cn"
UA = os.environ.get("CEAIR_UA") or (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")
# 浏览器环境画像：**通用桌面默认值**（不含任何本机信息），需要贴合自家设备时用环境变量覆盖：
#   CEAIR_CORES=8  CEAIR_MEM=8  CEAIR_TOUCH=0
#   CEAIR_SCREEN="1920,1080,1920,1040"  CEAIR_WIN="1440,813,1440,900"
def _pair(name, default):
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    try:
        vals = [int(v) for v in raw.replace("x", ",").split(",") if v.strip()]
    except ValueError:
        return list(default)
    return vals if len(vals) == 4 else list(default)


MACHINE = {
    "cores": int(os.environ.get("CEAIR_CORES", "8")),
    "mem": int(os.environ.get("CEAIR_MEM", "8")),
    "touch": int(os.environ.get("CEAIR_TOUCH", "0")),
    "screen": _pair("CEAIR_SCREEN", (1920, 1080, 1920, 1040)),
    "win": _pair("CEAIR_WIN", (1440, 813, 1440, 900)),
}

# 实测映射：xPos(拼图块 CSS left) = A·s² + B·s, s = 鼠标位移 = slidePos
MAPPING_A = 0.0035556
MAPPING_B = 0.07628
PIECE_CANVAS_OFFSET = 2        # 拼图块在自身 52px 画布内的左偏移
IMG_DISPLAY_SCALE = 300.0 / 296.0   # 背景 PNG 296px 被拉伸到 300px 容器

SDK_PATH = os.path.join(HERE, "sdk", "AliyunCaptcha.js")
SDK_JS = io.open(SDK_PATH, encoding="utf-8", errors="replace").read()

SHELL_HTML = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>机票预订_飞机票查询_东航官网</title></head>"
    "<body><div id='app'><div id='captcha-element' class='nc-container'></div></div></body></html>"
)

