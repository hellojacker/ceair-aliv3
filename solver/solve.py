# -*- coding: utf-8 -*-
"""一次完整求解的主流程（顺序即协议顺序，勿随意调换）。

    page.load 壳页 → 能力补丁 → 页面钩子 → 注入 SDK → initAliyunCaptcha
    → 循环 pump 直到拼图渲染 → 缺口识别 + 反解位移 → 人类式拖动 + 微调
    → 收割 param / success / 轨迹明文 / 网络往返证据
"""
import base64
import json
import os
import time

import iv8

from .bridge import Bridge
from .config import (
    HERE,
    IMG_DISPLAY_SCALE,
    PAGE_URL,
    PIECE_CANVAS_OFFSET,
    PREFIX,
    REGION,
    SCENE_ID,
    SDK_JS,
    SHELL_HTML,
)
from .env import build_env
from .gap import detect_gap, inverse_mapping
from .js.drag import DRAG_JS
from .js.hooks import HOOKS_JS
from .js.init import INIT_JS
from .js.patches import PATCH_JS, PATCH_STREAMS

def solve_once(with_callback=False, rounds_verbose=True, time_mode="system"):
    t0 = time.time()
    with iv8.JSContext(environment=build_env(), config={"timezone": "Asia/Shanghai"},
                       mode="prod", time_mode=time_mode) as ctx:
        ctx.eval("__iv8__.page.load(%s)" % json.dumps({"baseURL": PAGE_URL, "html": SHELL_HTML, "resources": {}}))
        br = Bridge(ctx, HERE)
        ctx.eval(PATCH_JS)
        ctx.eval(PATCH_STREAMS)
        ctx.eval(HOOKS_JS)
        ctx.eval(SDK_JS, name="AliyunCaptcha.js")
        ctx.eval(INIT_JS % (json.dumps(SCENE_ID), json.dumps(PREFIX), json.dumps(REGION),
                            "true" if with_callback else "false"))

        # 1) 初始化 + 渲染拼图（动态 JS/CSS + 网络桥接循环）
        ok = False
        for i in range(24):
            br.pump()
            ready = ctx.eval("!!document.querySelector('#aliyunCaptcha-sliding-slider') && "
                             "((document.querySelector('#aliyunCaptcha-img')||{}).src||'').length > 1000")
            if ready:
                ok = True
                break
        if not ok:
            raise RuntimeError("拼图控件未渲染（检查网络或 SDK 版本）")
        ctx.eval("(function(){try{window.__inst.show();}catch(e){}})()")
        br.pump(rounds=4)

        # 2) 缺口识别 + 反解位移
        back = os.path.join(HERE, "back.png")
        piece = os.path.join(HERE, "shadow.png")
        x_png = detect_gap(back, piece, verbose=rounds_verbose)
        hole_png = x_png + PIECE_CANVAS_OFFSET
        target = hole_png * IMG_DISPLAY_SCALE - PIECE_CANVAS_OFFSET
        s_est = inverse_mapping(target)
        if rounds_verbose:
            print("  缺口: 块 canvas x=%d → 缺口左边缘 %d(png) → 目标 xPos=%.1f → 位移 s=%.1f"
                  % (x_png, hole_png, target, s_est))

        # 3) 人类式拖动 + 微调（system 时间模式下需要放真实时间流逝）
        ctx.eval(DRAG_JS % (target, s_est, 100.0, 300.0))
        for k in range(300):
            br.pump(rounds=2, ms=26)
            time.sleep(0.012)
            if ctx.eval("!!(window.__sd && window.__sd.done)") and k > 3:
                break
        for k in range(120):
            br.pump(rounds=2, ms=26)
            time.sleep(0.012)
            if ctx.eval("!!(window.__probe && (window.__probe.success || window.__probe.param))"):
                break

        # 4) 收割
        param = ctx.eval("window.__probe && window.__probe.param ? String(window.__probe.param) : ''")
        success = ctx.eval("window.__probe && window.__probe.success ? String(window.__probe.success) : ''")
        trace = ctx.eval("JSON.stringify((window.__sd||{trace:[]}).trace)")
        snap = ctx.eval("JSON.stringify((window.__PLAIN||[]).slice(-1))") or "[]"
        plain = ""
        try:
            arr = json.loads(snap)
            if arr:
                plain = arr[-1]
                if plain.startswith("ENC::"):
                    plain = plain[5:]
        except Exception:
            pass
        out = {
            "param": json.loads(param) if param else None,
            "success": success,
            "successDecoded": None,
            "plaintext": plain,
            "trace": json.loads(trace) if trace else [],
            "gapPng": x_png,
            "target": target,
            "sEstimate": s_est,
            "initResponse": br.init_resp,
            "verifyRequest": br.verify_req,
            "verifyResponse": br.verify_resp,
            "elapsed": round(time.time() - t0, 1),
        }
        if success:
            try:
                out["successDecoded"] = base64.b64decode(success + "=" * (-len(success) % 4)).decode("utf-8", "replace")
            except Exception:
                pass
        return out, br.log

