# -*- coding: utf-8 -*-
"""命令行层：解析参数、控制重试轮次、判定 VerifyCode、把产物写盘。

只做"输入 → 调用 solve_once → 输出/落盘"，不放任何协议细节。
"""
import io
import json
import os
import re
import sys

from .config import HERE
from .solve import solve_once

def main():
    n = 1
    cb = False
    max_attempts = None
    for a in sys.argv[1:]:
        if a.startswith("--rounds="):
            n = int(a.split("=", 1)[1])
        if a.startswith("--until-t001="):
            max_attempts = int(a.split("=", 1)[1])
        if a == "--with-callback":
            cb = True
    if max_attempts is None:
        max_attempts = n
    got = 0
    for i in range(1, max_attempts + 1):
        print("=== 第 %d/%d 次离线求解 ===" % (i, max_attempts))
        out, netlog = solve_once(with_callback=cb)
        p = out.get("param") or {}
        succ = out.get("success") or ""
        dec = {}
        try:
            dec = json.loads(out.get("successDecoded") or "{}") or {}
        except Exception:
            dec = {}
        vr = {}
        try:
            vr = (json.loads(out.get("verifyResponse") or "{}").get("Result") or {})
        except Exception:
            vr = {}
        code = vr.get("VerifyCode", "?")
        print("  xPos=%-5s slidePos=%-5s VerifyCode=%-5s securityToken=%s" % (
            _field(out["plaintext"], "xPos"), _field(out["plaintext"], "slidePos"), code,
            ("有" if vr.get("securityToken") else "无")))
        if out.get("param"):
            print("  deviceToken=%d 字符 data=%d 字符" % (len(str(p.get("deviceToken") or "")),
                                                          len(str(p.get("data") or ""))))
        print("  success=%s  耗时=%ss" % (out.get("successDecoded"), out.get("elapsed")))
        if code == "T001":
            got += 1
        json.dump({"param": p, "success": succ, "successDecoded": out.get("successDecoded"),
                   "verifyCode": code, "verifyResponse": out.get("verifyResponse"),
                   "plaintext": out.get("plaintext"), "xPos": _field(out["plaintext"], "xPos"),
                   "slidePos": _field(out["plaintext"], "slidePos")},
                  io.open(os.path.join(HERE, "captcha_param.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        json.dump({k: v for k, v in out.items() if k != "param"},
                  io.open(os.path.join(HERE, "captcha_success.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        json.dump(netlog, io.open(os.path.join(HERE, "captcha_netlog.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        if code == "T001":
            print("  -> 服务器判决通过，停止重试")
            break
    print("\n通过 %d 次；已写出 captcha_param.json（含 securityToken）/ captcha_success.json / captcha_netlog.json" % got)
    return 0


def _field(plain, key):
    m = re.search(r'"%s":"([^"]*)"' % key, plain or "")
    return m.group(1) if m else "?"

