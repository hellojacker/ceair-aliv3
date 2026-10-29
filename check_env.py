# -*- coding: utf-8 -*-
"""ceair 虚拟环境自检：把"环境能跑"变成可重复的断言，而不是感觉。

用法（在 ceair 目录下）：
    .venv\\Scripts\\python.exe check_env.py

检查项：
  1. Python 版本 = 3.9.x（iv8 0.1.4 的 cp39 wheel）
  2. 关键包版本与 requirements.txt 一致
  3. iv8 引擎可用：V8 版本、JSContext 起得来、浏览器环境（window/document/navigator）在
  4. curl_cffi 能构造 impersonate=chrome 的会话
  5. 主脚本 ceair_solver.py 能被导入解析（不执行求解）
  6. RSA 后端自检（默认纯 Python：公钥解析 + pin 长度，不依赖 pycryptodome）
"""
import base64
import importlib
import os
import sys
import traceback

EXPECTED = {
    "iv8": "0.1.4",
    "curl_cffi": "0.13.0",
    "requests": "2.28.2",
    "numpy": "1.26.4",
    "PIL": "10.3.0",
}

ok = True


def line(flag, text):
    print(("  [OK]  " if flag else "  [FAIL] ") + text)
    return flag


print("=" * 68)
print("ceair 环境自检")
print("=" * 68)

# 1) Python 版本
ver = sys.version.split()[0]
ok &= line(ver.startswith("3.9."), "python %s  (%s)" % (ver, sys.executable))

# 2) 依赖版本
for mod, want in EXPECTED.items():
    try:
        m = importlib.import_module(mod)
        got = getattr(m, "__version__", "?")
        ok &= line(got == want, "%-11s %-8s (期望 %s)" % (mod, got, want))
    except Exception as e:  # noqa: BLE001
        ok &= line(False, "%-11s 导入失败: %s" % (mod, e))

# 2b) RSA 后端：默认纯 Python，不需要 pycryptodome（避杀软误报 pyc）
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import submit_requests as _sr
    _n, _e = _sr._rsa_pub_from_spki(_sr.PUB_KEY_B64)
    _pin = _sr.rsa_encrypt("123456")
    ok &= line(_n.bit_length() == 2048 and len(base64.b64decode(_pin)) == 256,
               "RSA 后端=%-11s 公钥 %d bit, pin %d 字符（无需 pycryptodome）"
               % (_sr.RSA_BACKEND, _n.bit_length(), len(_pin)))
except Exception as e:  # noqa: BLE001
    ok &= line(False, "RSA 自检失败: %s" % (e,))
try:
    import importlib.util as _ilu
    if _ilu.find_spec("Crypto") is not None:   # 只看装没装，不 import，避免生成 Crypto 下的 pyc
        print("  （备注：pycryptodome 已安装，仅交叉验证用；主链已不 import 它）")
except Exception:  # noqa: BLE001
    pass

# 3) iv8 引擎 + 浏览器环境 + __iv8__ 桥（真正做一次 page.load / DOM / eventLoop）
try:
    import json as _json
    import iv8

    print("  iv8 V8 引擎版本:", getattr(iv8, "v8_version", "?"))
    with iv8.JSContext(environment={}, config={"timezone": "Asia/Shanghai"}, mode="prod") as ctx:
        arith = ctx.eval("1+41")
        env = ctx.eval(
            "[typeof window, typeof document, typeof navigator, "
            "String(navigator.userAgent).indexOf('Chrome')>=0, "
            "String(navigator.languages)].join('|')"
        )
        ok &= line(arith == 42, "ctx.eval('1+41') = %r" % (arith,))
        ok &= line("object|object|object|true" in str(env), "浏览器环境: %s" % (env,))

        loaded = ctx.eval("__iv8__.page.load(%s)" % _json.dumps({
            "baseURL": "https://example.com/",
            "html": "<html><body><div id='probe'>ok</div></body></html>",
            "resources": {},
        }))
        ok &= line(isinstance(loaded, dict) and "executedScripts" in loaded,
                   "__iv8__.page.load -> %r" % (loaded,))
        ok &= line(ctx.eval("document.getElementById('probe').textContent") == "ok",
                   "DOM 可用: #probe = %r" % (ctx.eval("document.getElementById('probe').textContent"),))
        ok &= line(ctx.eval("__iv8__.eventLoop.tick(16), 'tick'" ) == "tick", "eventLoop.tick(16) 可推进")
        ok &= line(ctx.eval("window.__iv8__ !== undefined"), "window.__iv8__ 桥存在")
except Exception:
    ok &= line(False, "iv8 上下文跑不通:\n" + traceback.format_exc(limit=3))

# 4) curl_cffi
try:
    from curl_cffi import requests as creq
    s = creq.Session(impersonate="chrome")
    ok &= line(s is not None, "curl_cffi Session(impersonate=chrome) 构造成功")
except Exception as e:  # noqa: BLE001
    ok &= line(False, "curl_cffi 失败: %s" % (e,))

# 5) 主脚本可解析（compile 不执行）
try:
    src = open("ceair_solver.py", encoding="utf-8").read()
    compile(src, "ceair_solver.py", "exec")
    ok &= line(True, "ceair_solver.py 语法/编码 OK (%d 字节)" % len(src))
except Exception as e:  # noqa: BLE001
    ok &= line(False, "ceair_solver.py 无法编译: %s" % (e,))

print("-" * 68)
print("结论:", "环境就绪，可直接跑 ceair_solver.py" if ok else "有检查项失败，见上面 [FAIL]")
sys.exit(0 if ok else 1)
