# -*- coding: utf-8 -*-
"""纯 Python 提交与登录（等价替代 CDP 方案）：TLS 指纹用 curl_cffi 伪装 Chrome。

`cookies.json` 是**可选项**：有就带上（真机画像/站点会话更贴近），没有就直接无 cookie 跑
——实测 WAF 只看 TLS/HTTP2 指纹，无 cookie 同样能拿到业务 JSON。所以不需要为了它去跑 CDP 导 cookie。

子命令：
  （无参数）                         交互式向导：输入手机号 → 选参数来源 → 发码 → 输入验证码 → 登录 → 验收
  probe                              探针：打 check/token（不发短信），只看 WAF 是否放行
  send   <手机号>                    发短信验证码（需已有 T001 的 success，或加 --solve 现解）
  login  <手机号>                    用已有产物 + 手动输入验证码 → 登录 → 换 token → 验收
  flow   <手机号>                    一条龙：求解 → 发码 → 手动输入 → 登录 → 验收 → 存 session.json
  status                             用 session.json 打 check/token，看是否仍登录、token 是否有效
  token                             打印已登录的 tokenKey / 关键 cookie；可 --export=headers.txt 导出 Cookie 头

通用选项：
  --solve              现解滑块（iv8 离线，判到 T001 才提交）
  --solve-rounds=N     求解最多几轮（默认 6；单轮 3–8s，命中即停）
  --reuse=SEC          若 captcha_param.json 是 SEC 秒内的 T001 产物就直接复用，跳过求解
  --wait=N             发码前冷却秒数（默认 40；同号 30s 内重复发码会 A500）
  --no-cool            跳过冷却
  --param=FILE         指定产物文件（默认 captcha_param.json）
  --code=123456        非交互：直接给短信验证码（不给则交互式 input）
  --session=FILE       会话落盘路径（默认 session.json）
  --backend=curl|req   传输后端（默认 auto=curl_cffi，回落 requests）
  --imp=chrome         伪装版本（chrome / chrome131 …）
  --nocookie           不使用 cookies.json 里的 cookie（没有该文件时等价于默认行为）
  --dry-run            只打印将要发送的请求体（pin 打码），不发请求

退出码：0=成功（A200/已登录） / 2=被 WAF 拦 / 3=业务未通过 / 4=参数缺失

登录接口（docs/api_map.md §4）：
  POST /mumember/api/sso/login
  {"salesChannel":"7690","captchaVerifyParam":"<T001 的 success>",
   "account":"<手机号>","accountType":"MOBILE","pin":"<RSA_PKCS1_v1_5(短信码) base64>","telephoneCode":"86"}
  成功 resultCode=A200，resultContent 含 userId/passwordType 等，会话凭证落在 Set-Cookie。
  验收：POST /mumember/api/sso/check/token {"salesChannel":"7690"} → A200 即登录态有效。
"""
import base64
import io
import json
import os
import re
import sys
import time
import uuid


def _setup_stdout():
    """把 stdout 换成 UTF-8 + 行缓冲，并（Windows 控制台）先把代码页切到 65001，
    这样双击运行也不会中文乱码，且求解/冷却进度逐行可见。"""
    if os.name == "nt":
        try:
            if sys.stdout.isatty():
                os.system("chcp 65001 > nul 2>&1")
        except Exception:
            pass
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace", line_buffering=True)
    except Exception:
        pass


_setup_stdout()
HERE = os.path.dirname(os.path.abspath(__file__))

BASE = "https://sso.ceair.com"
CODE_URL = BASE + "/mumember/api/sso/get/password/code"
CHECK_URL = BASE + "/mumember/api/sso/check/token"
LOGIN_URL = BASE + "/mumember/api/sso/login"
LOGIN_PAGE = "https://sso.ceair.com/new/login?type=mobile"

SALES_CHANNEL = "7690"          # zh 站点；en 站点为 7696（docs/api_map.md §4）
TELEPHONE_CODE = "86"
# 站点 RSA 公钥（JSEncrypt 3.0.0-rc.1，2048-bit SPKI；证据见 docs/api_map.md §4.1）
PUB_KEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqLmyqJ6IEzP6lWOsQrJc3KWERH89l/qtzwt9ws1UJrN/"
    "j6o/rsAkYs+mSBCxTI9HhGMNkKpklycYGxUg0Qr4lF+V5sK4oe5BvrTQamdjqphBLHqtRPgp1pXMUT/uNnLwhitxc"
    "GhxowoFscmlu2zmjh1EtLhTdz2GhZrcVFbyV2FeRGCpUfNrxAgRms8V6GDT7GA5JZfG2ALveX+UANHab7UWF6XBKIQa"
    "+k1IgDvltSOiftWu1+3oIfieZSYsAmCgovuxvDduI0cpNoIf1Q40p9p9HPCd/4ud9V44nOfv5TXzoi90w9RcDQr6dRp"
    "SB2b0B+wRqa5aFD5654Oph/WDiwIDAQAB"
)

TOKEN_HINT = re.compile(r"(token|ticket|jwt|auth|session|sid)", re.I)


# ─────────────────────────── 基础：cookies / 头 / 会话 ───────────────────────────
def empty_profile():
    """无 cookie 运行时用的空画像：只有默认 UA + 随机 ssoUserId。"""
    return {"env": {}, "cookies": {}, "site_sso_user_id": None, "exported_at": int(time.time())}


def load_cookies(ignore_cookies=False):
    """cookies.json 是**可选**的。

    实测 WAF 只看 TLS/HTTP2 指纹（curl_cffi impersonate 就够），不带 cookie 也能拿到业务 JSON；
    cookie 只在"需要站点会话/登录态"时才影响结果。所以：没有文件就直接按无 cookie 跑，不再拦下流程。
    """
    p = os.path.join(HERE, "cookies.json")
    if ignore_cookies:
        print("--nocookie：忽略 cookies.json，按无 cookie 运行")
        return empty_profile()
    if not os.path.exists(p):
        print("没有 cookies.json —— 直接按无 cookie 运行"
              "（WAF 只看 TLS 指纹，实测可过；不需要为此跑 cdp/export_cookies.py）")
        return empty_profile()
    try:
        d = json.load(io.open(p, encoding="utf-8"))
    except Exception as e:
        print("cookies.json 解析失败（%s）—— 按无 cookie 运行" % str(e)[:60])
        return empty_profile()
    age = int(time.time()) - int(d.get("exported_at") or 0)
    if age > 1800:
        print("cookies.json 已导出 %d 分钟（可能过期）：仍会带上，过期不影响 WAF 放行，"
              "只影响需要登录态的字段；要刷新再跑 cdp/export_cookies.py，不跑也行" % (age // 60))
    return d


def build_headers(d):
    env = d.get("env") or {}
    return {
        "User-Agent": env.get("ua") or ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                        "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"),
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh_CN",
        "Site": "zh_CN",
        "ssoUserId": d.get("site_sso_user_id") or str(uuid.uuid4()),
        "Origin": "https://sso.ceair.com",
        "Referer": LOGIN_PAGE,
    }


def make_session(d, backend="auto", imp="chrome", use_cookies=True, cookies=None):
    headers = build_headers(d)
    jar = cookies if cookies is not None else ((d.get("cookies") or {}) if use_cookies else {})
    if backend in ("auto", "curl"):
        try:
            from curl_cffi import requests as creq
            s = creq.Session(impersonate=imp)
            if jar:
                s.cookies.update(jar)
            return "curl_cffi(%s)%s" % (imp, "+cookie" if jar else "-nocookie"), s, headers
        except Exception as e:
            if backend == "curl":
                print("!! curl_cffi 不可用:", str(e)[:80])
                sys.exit(4)
    import requests
    s = requests.Session()
    if jar:
        s.cookies.update(jar)
    return "requests%s" % ("+cookie" if jar else "-nocookie"), s, headers


def is_waf(r):
    body = (r.text or "")
    ct = (r.headers.get("content-type") or "")
    return r.status_code == 403 or "403 Forbidden" in body[:600] or "Try again later" in body[:600] \
        or ("json" not in ct and "<html" in body[:200].lower())


def post(s, headers, url, payload, tag):
    t0 = time.time()
    try:
        r = s.post(url, data=json.dumps(payload, ensure_ascii=False), headers=headers, timeout=30)
    except Exception as e:
        print("  %-12s EXC %s" % (tag, str(e)[:150]))
        return None
    print("  %-12s HTTP %s %dms  ct=%s" % (tag, r.status_code, int((time.time() - t0) * 1000),
                                           (r.headers.get("content-type") or "")[:38]))
    print("     body: %s" % (r.text or "")[:300].replace("\n", " "))
    return r


def parse_json(r):
    try:
        return json.loads(r.text)
    except Exception:
        return None


def dump_cookies(s):
    try:
        return {k: v for k, v in s.cookies.get_dict().items()}
    except Exception:
        return {}


# ─────────────────────────── RSA（对应站点 JSEncrypt） ───────────────────────────
# 默认用纯 Python 实现：**不 import pycryptodome**。
# 原因：`Crypto.PublicKey.RSA` 会连带 import `Crypto.IO.PEM` → `Crypto.Protocol.KDF`，
# pip 安装时又会预编译出 `Crypto/Protocol/__pycache__/KDF.cpython-39.pyc`；
# 这个 pyc 常被杀软按启发式误报，且每次调用都会重新产生。绕开它最省事。
# 想要库实现可设 CEAIR_RSA=pycryptodome。
RSA_BACKEND = os.environ.get("CEAIR_RSA", "pure").strip().lower()


def _der_tlv(buf, i):
    """读一个 DER TLV，返回 (tag, value, next_index)。只处理定长长度。"""
    tag = buf[i]
    i += 1
    ln = buf[i]
    i += 1
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(buf[i:i + k], "big")
        i += k
    return tag, buf[i:i + ln], i + ln


def _rsa_pub_from_spki(b64):
    """从 SubjectPublicKeyInfo(base64) 取出 (n, e)，不依赖任何第三方库。"""
    der = base64.b64decode(b64)
    tag, body, _ = _der_tlv(der, 0)                 # SEQUENCE
    tag, alg, off = _der_tlv(body, 0)               # SEQUENCE AlgorithmIdentifier
    tag, bits, _ = _der_tlv(body, off)              # BIT STRING
    if tag != 0x03:
        raise ValueError("不是 BIT STRING 结构")
    inner = bits[1:]                                # 跳过 unused-bits 字节
    tag, seq, _ = _der_tlv(inner, 0)                # SEQUENCE RSAPublicKey
    tag, nb, off = _der_tlv(seq, 0)                 # INTEGER n
    tag, eb, _ = _der_tlv(seq, off)                 # INTEGER e
    return int.from_bytes(nb, "big"), int.from_bytes(eb, "big")


def pkcs1v15_pad(msg, k):
    """EM = 0x00 || 0x02 || PS(全非零随机, >=8) || 0x00 || M（RFC 8017 §7.2.1）。"""
    if len(msg) > k - 11:
        raise ValueError("明文过长：%d > %d" % (len(msg), k - 11))
    ps = bytearray()
    while len(ps) < k - len(msg) - 3:
        b = os.urandom(1)[0]
        if b:
            ps.append(b)
    return b"\x00\x02" + bytes(ps) + b"\x00" + msg


def rsa_encrypt(plain, backend=None):
    """JSEncrypt 等价：RSAES-PKCS1-v1_5 + base64。

    站点 bundle：`RSAencrypt:function(e,t){var i=new de.a;return i.setPublicKey(t),i.encrypt(e)}`，
    库为 JSEncrypt 3.0.0-rc.1（docs/api_map.md §4.1）。JSEncrypt 默认就是 PKCS#1 v1.5。
    """
    be = (backend or RSA_BACKEND or "pure").lower()
    if be in ("crypto", "pycryptodome", "lib"):
        from Crypto.PublicKey import RSA          # 仅显式指定时才用库
        from Crypto.Cipher import PKCS1_v1_5
        key = RSA.import_key(base64.b64decode(PUB_KEY_B64))
        if key.size_in_bits() != 2048:
            raise ValueError("公钥不是 2048-bit（%d）" % key.size_in_bits())
        return base64.b64encode(PKCS1_v1_5.new(key).encrypt(plain.encode("utf-8"))).decode()

    n, e = _rsa_pub_from_spki(PUB_KEY_B64)
    k = (n.bit_length() + 7) // 8
    if k != 256:
        raise ValueError("公钥模长不是 2048-bit（%d 字节）" % k)
    em = pkcs1v15_pad(plain.encode("utf-8"), k)
    c = pow(int.from_bytes(em, "big"), e, n)
    return base64.b64encode(c.to_bytes(k, "big")).decode()


def mask_pin(pin):
    return pin[:16] + "…" + pin[-8:] + "(%d 字符)" % len(pin)


# ─────────────────────────── 产物读取 ───────────────────────────
def _artifact_age(path):
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return None


def load_success(param_file="captcha_param.json", do_solve=False, max_rounds=6, reuse_fresh=0):
    """取 T001 的 success（提交时的 captchaVerifyParam）。

    do_solve=True 时逐轮求解并**实时打印进度**（每轮多少秒、当前判定），
    避免"看起来卡住"——单轮 3–8s，最多 max_rounds 轮。
    """
    p = os.path.join(HERE, param_file)

    if do_solve and reuse_fresh and os.path.exists(p):
        age = _artifact_age(p) or 1e9
        try:
            d0 = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            d0 = {}
        if age <= reuse_fresh and d0.get("verifyCode") == "T001" and d0.get("success"):
            print("复用 %.0f 秒前的 T001 产物（--reuse=%d，跳过求解）" % (age, reuse_fresh))
            return d0["success"]

    if do_solve:
        sys.path.insert(0, HERE)
        import ceair_solver
        print("== iv8 离线求解到 T001（单轮约 3–8s，最多 %d 轮；每轮末打印判定）==" % max_rounds,
              flush=True)
        t0 = time.time()
        out = None
        for i in range(1, max_rounds + 1):
            print("  [%5.1fs] 第 %d/%d 轮：起 iv8 → 拉动态 JS → 缺口识别 → 拖动 → 等判决…"
                  % (time.time() - t0, i, max_rounds), flush=True)
            t_round = time.time()
            out, _ = ceair_solver.solve_once()
            vr = json.loads(out.get("verifyResponse") or "{}").get("Result") or {}
            code = vr.get("VerifyCode")
            print("  [%5.1fs] 第 %d 轮完成 %.1fs：VerifyCode=%s xPos=%s%s"
                  % (time.time() - t0, i, time.time() - t_round, code,
                     ceair_solver._field(out["plaintext"], "xPos"),
                     "  ✅ 命中" if code == "T001" else "  → 继续"),
                  flush=True)
            if code == "T001":
                break
        print("  求解阶段共 %.1fs" % (time.time() - t0), flush=True)
        succ = out.get("success") or ""
        io.open(os.path.join(HERE, "captcha_param.json"), "w", encoding="utf-8").write(json.dumps(
            {"param": out.get("param"), "success": succ, "successDecoded": out.get("successDecoded"),
             "verifyCode": "T001", "verifyResponse": out.get("verifyResponse"),
             "plaintext": out.get("plaintext"),
             "xPos": ceair_solver._field(out.get("plaintext"), "xPos")}, ensure_ascii=False, indent=1))
        return succ

    if not os.path.exists(p):
        print("!! 没有 %s；加 --solve 现解，或先跑 ceair_solver.py" % param_file)
        sys.exit(4)
    d2 = json.load(io.open(p, encoding="utf-8"))
    age = _artifact_age(p)
    print("使用已有产物: verifyCode=%s certifyId=%s（%.0f 秒前生成，>60s 就基本作废，建议加 --solve）"
          % (d2.get("verifyCode"), (json.loads(d2.get("successDecoded") or "{}") or {}).get("certifyId"),
             age or 0))
    return d2.get("success") or ""


def cooldown(sec, label="发码前冷却"):
    """可视化冷却：每 5s 报一次剩余，避免看起来像卡死。"""
    if sec <= 0:
        return
    print("%s %ds（服务端要求同号 ≥30s 内不重复发码）…" % (label, sec), flush=True)
    left = sec
    while left > 0:
        step = min(5, left)
        time.sleep(step)
        left -= step
        print("  剩余 %ds…" % left if left else "  冷却结束，开始发码", flush=True)


# ─────────────────────────── 发验证码 ───────────────────────────
def send_code(s, headers, phone, captcha):
    r = post(s, headers, CODE_URL, send_body(phone, captcha), "sendCode")
    return r, (parse_json(r) if r is not None else None)


def send_body(phone, succ):
    return {"channelType": "CN", "salesChannel": SALES_CHANNEL,
            "captchaVerifyParam": succ, "phone": phone, "telephoneCode": TELEPHONE_CODE}


def cmd_send(d, phone, wait, do_solve, param_file, no_cool, backend, imp, use_cookies=True,
             dry_run=False, solve_rounds=6, reuse_fresh=0):
    succ = load_success(param_file, do_solve, max_rounds=solve_rounds, reuse_fresh=reuse_fresh)
    if not succ:
        print("!! 没有 success 值")
        return 4
    if dry_run:
        print("\n[dry-run] POST %s" % CODE_URL)
        print(json.dumps(dict(send_body(phone, "<T001 的 success>"),
                              captchaVerifyParam=brief(succ, 24)), ensure_ascii=False, indent=1))
        print("\n[dry-run] 未发送任何请求（去掉 --dry-run 才真发短信）")
        return 0
    if not no_cool:
        cooldown(wait)

    name, s, h = make_session(d, backend, imp, use_cookies)
    print("backend:", name)
    r, body = send_code(s, h, phone, succ)
    if r is None:
        return 3
    if is_waf(r):
        print("\n⇒ 被 WAF 拦")
        return 2
    if not body:
        print("\n⇒ 非 JSON 响应")
        return 3
    code, msg = str(body.get("resultCode")), str(body.get("resultMsg"))
    print("\n=== 判定 ===")
    if code == "A200":
        print("✅ A200 Success —— 短信已发 %s；下一步：python submit_requests.py login %s" % (phone, phone))
        return 0
    if code == "A500" and "30秒" in msg:
        print("⏳ 频率限制：%s —— 等 40s 重试" % msg)
        return 3
    print("❌ %s %s" % (code, msg))
    return 3


# ─────────────────────────── 登录 / 验收 / token ───────────────────────────
def prompt_code(given=None):
    if given:
        code = str(given).strip()
    else:
        try:
            code = input("请输入短信收到的验证码（回车提交）：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            sys.exit(4)
    if not code:
        print("!! 没输入验证码")
        sys.exit(4)
    if not re.fullmatch(r"\d{4,8}", code):
        print("!! 验证码应为 4-8 位数字，收到 %r" % code)
        sys.exit(4)
    return code


def find_tokens(result_content, cookies):
    """从 resultContent 与 cookie 里挑出疑似凭证，供报告与后续复用。"""
    out = {}
    if isinstance(result_content, dict):
        for k, v in result_content.items():
            if isinstance(v, (str, int)) and v not in ("", None) and TOKEN_HINT.search(k):
                out["resultContent." + k] = v
    for k, v in (cookies or {}).items():
        if TOKEN_HINT.search(k) and v:
            out["cookie." + k] = v
    return out


def brief(v, n=28):
    s = str(v)
    return s if len(s) <= n else "%s…(%d)" % (s[:n], len(s))


def save_session(path, payload):
    p = path if os.path.isabs(path) else os.path.join(HERE, path)
    io.open(p, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))
    print("已写入 %s（含会话 cookie，请按凭据对待）" % p)


def check_token(s, headers, tag="check/token"):
    r = post(s, headers, CHECK_URL, {"salesChannel": SALES_CHANNEL}, tag)
    if r is None:
        return None, None
    return r, parse_json(r)


def build_login_body(phone, code, captcha, sales_channel=SALES_CHANNEL, telephone_code=TELEPHONE_CODE):
    """按站点 `tologin()` 的字段与顺序拼登录请求体（顺序与 Object.assign 结果一致）。

    bundle 证据：`a={salesChannel:…, captchaVerifyParam:e}` → `Object.assign({},a,{account,accountType,pin})`
    → MOBILE 追加 `telephoneCode`（docs/api_map.md §4.1）。字段顺序保留，便于与真机抓包逐字段 diff。
    """
    body = {
        "salesChannel": sales_channel,
        "captchaVerifyParam": captcha,
        "account": phone,
        "accountType": "MOBILE",
        "pin": rsa_encrypt(code),
        "telephoneCode": telephone_code,
    }
    return body


def cmd_login(d, phone, code, param_file, session_file, backend, imp, use_cookies=True,
              s=None, headers=None, backend_name=None, captcha=None, dry_run=False):
    succ = captcha if captcha is not None else load_success(param_file, False)
    if not succ:
        print("!! 没有 success 值（先跑 send 或 ceair_solver.py）")
        return 4
    code = str(code or "123456") if dry_run else prompt_code(code)
    body = build_login_body(phone, code, succ)
    pin = body["pin"]
    if dry_run:
        shown = dict(body, pin=mask_pin(pin), captchaVerifyParam=brief(succ, 24))
        print("\n[dry-run] POST %s" % LOGIN_URL)
        print(json.dumps(shown, ensure_ascii=False, indent=1))
        print("\n[dry-run] pin 长度 %d（应为 344 = 256 字节 base64），未发送任何请求" % len(pin))
        return 0

    if s is None:
        name, s, headers = make_session(d, backend, imp, use_cookies)
    else:
        name = backend_name or "reused-session"
    print("backend:", name)
    r = post(s, headers, LOGIN_URL, body, "login")
    if r is None:
        return 3
    if is_waf(r):
        print("\n⇒ 被 WAF 拦")
        return 2
    res = parse_json(r) or {}
    rc, msg = str(res.get("resultCode")), str(res.get("resultMsg"))
    content = res.get("resultContent")

    print("\n=== 登录判定 ===")
    if rc != "A200":
        # 站点错误码：14=高风险二段，10150114/115/116=强制改密/找回
        hint = {"14": "高风险二次身份验证（需 verifyCode + codeDestination）",
                "10150114": "需重置密码", "10150115": "需找回密码", "10150116": "需立即修改密码"}.get(rc, "")
        print("❌ %s %s %s" % (rc, msg, ("—— " + hint) if hint else ""))
        return 3
    print("✅ A200 登录成功；resultContent = %s" % json.dumps(content, ensure_ascii=False)[:400])

    cookies = dump_cookies(s)
    print("Set-Cookie 后共 %d 个 cookie: %s" % (len(cookies), ", ".join(sorted(cookies))[:260]))

    print("\n=== 登录态验收（check/token） ===")
    r2, check = check_token(s, headers)
    check_ok = bool(r2 is not None and not is_waf(r2) and str((check or {}).get("resultCode")) == "A200")
    if check:
        print("  resultCode=%s resultContent=%s" % (
            check.get("resultCode"), json.dumps(check.get("resultContent"), ensure_ascii=False)[:300]))
    print(("✅ 已登录（check/token A200）" if check_ok else "⚠️ check/token 未返回 A200，登录态可能不完整"))

    tokens = find_tokens(content, cookies)
    tokens.update({"check." + k: v for k, v in find_tokens((check or {}).get("resultContent"), {}).items()})
    if tokens:
        print("\n=== 疑似凭证（token / 会话） ===")
        for k, v in tokens.items():
            print("  %-34s %s" % (k, brief(v)))
    else:
        print("\n（未发现显式 token 字段；会话凭证以 cookie 形式存在，见下）")

    save_session(session_file, {
        "saved_at": int(time.time()), "phone": phone, "accountType": "MOBILE",
        "login_resultCode": rc, "resultContent": content,
        "cookies": cookies, "cookie_list": dump_cookies(s),
        "check_resultCode": (check or {}).get("resultCode"),
        "check_resultContent": (check or {}).get("resultContent"),
        "tokens": tokens, "backend": name, "headers": headers,
    })
    return 0 if (rc == "A200" and check_ok) else 3


def cmd_flow(d, phone, wait, do_solve, param_file, no_cool, code, session_file,
             backend, imp, use_cookies=True, dry_run=False, solve_rounds=6, reuse_fresh=0):
    """求解 → 发码 → 手动输入 → 登录 → 验收 → 落盘。全程同一个 session（cookie 连续）。"""
    t_flow = time.time()
    succ = load_success(param_file, do_solve, max_rounds=solve_rounds, reuse_fresh=reuse_fresh)
    if not succ:
        print("!! 没有 success 值")
        return 4
    if dry_run:
        pin = rsa_encrypt(str(code or "123456"))
        print("\n[dry-run] 本次会依次发这两个请求：\n")
        print("① POST %s" % CODE_URL)
        print(json.dumps(dict(send_body(phone, "<T001 的 success>"),
                              captchaVerifyParam=brief(succ, 24)), ensure_ascii=False, indent=1))
        print("\n② POST %s   ← 等你输入短信码后" % LOGIN_URL)
        print(json.dumps({"salesChannel": SALES_CHANNEL, "captchaVerifyParam": brief(succ, 24),
                          "account": phone, "accountType": "MOBILE", "pin": mask_pin(pin),
                          "telephoneCode": TELEPHONE_CODE}, ensure_ascii=False, indent=1))
        print("\n[dry-run] 未发送任何请求（去掉 --dry-run 才会真发短信 / 真登录）")
        return 0
    t_solve = time.time() - t_flow
    if not no_cool:
        print("提示：接下来是 %ds 冷却（服务端要求），这段时间没有任何输出是正常的。" % wait, flush=True)
        cooldown(wait)
    t_send0 = time.time()

    name, s, h = make_session(d, backend, imp, use_cookies)
    print("backend:", name)
    r, body = send_code(s, h, phone, succ)
    if r is None:
        return 3
    if is_waf(r):
        print("\n⇒ 被 WAF 拦")
        return 2
    if not body or str(body.get("resultCode")) != "A200":
        print("❌ 发码失败：%s %s" % ((body or {}).get("resultCode"), (body or {}).get("resultMsg")))
        return 3
    print("✅ 短信已发 %s（60s 内有效；同号 30s 内勿重复发）" % phone)
    t_send = time.time() - t_send0

    # 登录复用同一个 session：captchaVerifyParam 用刚才那串（站点自身也是这样复用）
    rc = cmd_login(d, phone, code, param_file, session_file, backend, imp, use_cookies,
                   s=s, headers=h, backend_name=name, captcha=succ)
    print("\n=== 分阶段耗时 ===")
    print("  求解 %.1fs │ 冷却 %ds │ 发码 %.1fs │ 登录+验收 %.1fs │ 合计 %.1fs"
          % (t_solve, 0 if no_cool else wait, t_send,
             time.time() - t_flow - t_solve - t_send - (0 if no_cool else wait), time.time() - t_flow))
    return rc


def _load_session(session_file):
    p = session_file if os.path.isabs(session_file) else os.path.join(HERE, session_file)
    if not os.path.exists(p):
        print("!! 没有 %s（先跑 login 或 flow）" % p)
        return None, None
    return p, json.load(io.open(p, encoding="utf-8"))


def cmd_status(session_file):
    p, prev = _load_session(session_file)
    if prev is None:
        return 4
    print("会话: phone=%s 登录于 %s backend=%s" % (
        prev.get("phone"), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(prev.get("saved_at") or 0)),
        prev.get("backend")))
    d = {"env": {"ua": (prev.get("headers") or {}).get("User-Agent", "")},
         "cookies": {}, "site_sso_user_id": None}
    name, s, h = make_session(d, "auto", "chrome", True, cookies=prev.get("cookies") or {})
    print("backend:", name)
    r, check = check_token(s, h, "check/token")
    if r is None:
        return 3
    if is_waf(r):
        print("\n⇒ 被 WAF 拦")
        return 2
    rc = str((check or {}).get("resultCode"))
    print("resultCode=%s resultContent=%s" % (rc, json.dumps((check or {}).get("resultContent"),
                                                             ensure_ascii=False)[:300]))
    if rc == "A200":
        # 服务端可能在 check 时轮换 cookie，顺手把最新会话写回，避免下次失效
        fresh = dump_cookies(s)
        if fresh and fresh != (prev.get("cookies") or {}):
            prev["cookies"] = fresh
            prev["cookie_list"] = fresh
            prev["check_resultCode"] = rc
            prev["check_resultContent"] = (check or {}).get("resultContent")
            prev["saved_at"] = int(time.time())
            prev["tokens"] = find_tokens(prev.get("resultContent"), fresh)
            save_session(p, prev)
        print("✅ 登录态有效")
        return 0
    print("❌ 登录态失效（重新 login）")
    return 3


def cmd_token(session_file, export=None, refresh=False):
    """把已登录会话里的 token / Cookie 打印或导出，供其它请求复用。"""
    p, prev = _load_session(session_file)
    if prev is None:
        return 4
    if refresh:
        d = {"env": {"ua": (prev.get("headers") or {}).get("User-Agent", "")},
             "cookies": {}, "site_sso_user_id": None}
        name, s, h = make_session(d, "auto", "chrome", True, cookies=prev.get("cookies") or {})
        r, check = check_token(s, h, "check/token")
        if r is not None and not is_waf(r) and str((check or {}).get("resultCode")) == "A200":
            prev["cookies"] = dump_cookies(s)
            prev["cookie_list"] = prev["cookies"]
            prev["tokens"] = find_tokens(prev.get("resultContent"), prev["cookies"])
            prev["saved_at"] = int(time.time())
            save_session(p, prev)
        else:
            print("（refresh 失败，沿用已保存的会话）")

    rc = prev.get("resultContent") or {}
    token = rc.get("tokenKey") or ""
    cookies = prev.get("cookies") or {}
    print("userId=%s  phone=%s  accountType=%s  登录于 %s" % (
        rc.get("userId"), prev.get("phone"), rc.get("accountType"),
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(prev.get("saved_at") or 0))))
    print("tokenKey : %s" % token)
    for name in ("access_token", "ceair.login.token", "com.ceair.cesso"):
        if name in cookies:
            same = "（= tokenKey）" if cookies[name] == token else ""
            print("cookie.%s : %s%s" % (name, cookies[name], same))
    print("共 %d 个 cookie" % len(cookies))

    cookie_hdr = "Cookie: " + "; ".join("%s=%s" % (k, v) for k, v in cookies.items())
    if export:
        path = export if os.path.isabs(export) else os.path.join(HERE, export)
        io.open(path, "w", encoding="utf-8").write(
            "# 由 submit_requests.py token 导出，含会话凭证，勿外传\n%s\n" % cookie_hdr)
        print("\n已导出请求头到 %s（%d 字节）" % (path, os.path.getsize(path)))
    else:
        print("\n可直接复用的请求头（片段）：\n%s…" % cookie_hdr[:120])
        print("（要完整导出：python submit_requests.py token --export=headers.txt）")
    print("\n⚠️ tokenKey 与 Cookie 等同于登录态，别贴到公开地方；怀疑泄露就重新登录换一个。")
    return 0


# ─────────────────────────── 交互式向导（无参数直接运行） ───────────────────────────
def _ask(text, default=""):
    try:
        v = input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        sys.exit(4)
    return v or default


def prompt_phone():
    while True:
        raw = _ask("请输入手机号（11 位，输入 q 退出）：")
        if raw.lower() in ("q", "quit", "exit"):
            return None
        digits = re.sub(r"\D", "", raw)
        if digits.startswith("86") and len(digits) == 13:
            digits = digits[2:]
        if re.fullmatch(r"1\d{10}", digits):
            return digits
        print("  格式不对：应为 1 开头的 11 位数字（可带 +86）")


def _choose(title, options, default=1):
    print(title)
    for i, (label, _) in enumerate(options, 1):
        print("  %d) %s" % (i, label))
    raw = _ask("选择 [回车 = %d]：" % default, str(default))
    try:
        idx = int(raw)
    except ValueError:
        idx = default
    idx = max(1, min(idx, len(options)))
    return options[idx - 1][1]


def cmd_interactive(dry_run=False, wait=40, rounds=6):
    """无参数运行时的向导：问手机号 → 选参数来源 →（默认冷却 40s / 6 轮）→ 发码 → 输验证码 → 登录 → 验收。

    冷却与求解轮数不再逐项询问；要改就带命令行参数：login.cmd --wait=0 --solve-rounds=3
    """
    print("=" * 64)
    print(" 东航登录一键流程：求解滑块 → 发短信 → 输入验证码 → 登录 → 验收")
    print("=" * 64)
    art = os.path.join(HERE, "captcha_param.json")
    sess = os.path.join(HERE, "session.json")
    age = _artifact_age(art) if os.path.exists(art) else None
    print("当前产物：%s" % (("captcha_param.json 约 %.0f 秒前生成" % age) if age is not None
                          else "无（会先求解滑块）"))
    if os.path.exists(sess):
        try:
            s0 = json.load(io.open(sess, encoding="utf-8"))
            print("已有会话：phone=%s 登录于 %s（可用 python submit_requests.py status 复查）"
                  % (s0.get("phone"),
                     time.strftime("%m-%d %H:%M", time.localtime(s0.get("saved_at") or 0))))
        except Exception:
            pass
    print("")

    phone = prompt_phone()
    if not phone:
        print("已退出")
        return 1

    mode = _choose("滑块参数从哪来？", [
        ("现解滑块（约 3–20s，最稳）", "solve"),
        ("复用 2 分钟内的 T001 产物（快）", "reuse"),
        ("直接用现有 captcha_param.json（可能已过期）", "any"),
    ], default=1)

    print("\n将执行：手机号 %s ｜ 参数=%s ｜ 冷却 %ds ｜ %s"
          "（改默认值：加 --wait=N / --solve-rounds=N）"
          % (phone, {"solve": "现解", "reuse": "复用 2 分钟内产物", "any": "用现有产物"}[mode],
             wait, ("最多 %d 轮求解" % rounds) if mode == "solve" else "不求解"))

    if dry_run:
        print("\n[dry-run] 未执行任何请求。真实请求会是：")
        print("① POST %s" % CODE_URL)
        print(json.dumps({"channelType": "CN", "salesChannel": SALES_CHANNEL,
                          "captchaVerifyParam": "<T001 success>", "phone": phone,
                          "telephoneCode": TELEPHONE_CODE}, ensure_ascii=False, indent=1))
        print("\n② POST %s   ← 你输入短信码后" % LOGIN_URL)
        print(json.dumps({"salesChannel": SALES_CHANNEL, "captchaVerifyParam": "<T001 success>",
                          "account": phone, "accountType": "MOBILE",
                          "pin": "<RSA_PKCS1_v1_5(短信码) 344 字符>",
                          "telephoneCode": TELEPHONE_CODE}, ensure_ascii=False, indent=1))
        print("\n（正式运行：去掉 --dry-run，或直接双击 login.cmd）")
        return 0

    d = load_cookies()
    try:
        rc = cmd_flow(d, phone, wait, mode == "solve", "captcha_param.json", wait == 0, None,
                      "session.json", "auto", "chrome", True, dry_run=False,
                      solve_rounds=rounds, reuse_fresh=120 if mode == "reuse" else 0)
    except SystemExit as e:            # 中途取消（比如没输验证码）
        print("\n流程中止（code=%s）" % e.code)
        rc = e.code if isinstance(e.code, int) else 1

    print("")
    if rc == 0:
        print("✅ 完成。下一步可查看/复用登录态：")
        print("   python submit_requests.py token")
        print("   python tools\\probe_session.py")
    else:
        print("❌ 未完成（退出码 %s）。可单独重试某一步：" % rc)
        print("   python submit_requests.py send  %s --no-cool" % phone)
        print("   python submit_requests.py login %s" % phone)
    if sys.stdin is not None and sys.stdin.isatty() and not os.environ.get("CEAIR_NO_PAUSE"):
        try:
            input("\n按回车退出…")
        except (EOFError, KeyboardInterrupt):
            pass
    return rc


# ─────────────────────────── CLI ───────────────────────────
def cmd_probe(d, backend, imp, use_cookies=True):
    name, s, h = make_session(d, backend, imp, use_cookies)
    print("backend:", name)
    r = post(s, h, CHECK_URL, {"salesChannel": SALES_CHANNEL}, "probe")
    if r is None or is_waf(r):
        print("\n⇒ 被 WAF 拦（该指纹/该 cookie 组合不被接受）")
        return 2
    print("\n⇒ WAF 放行（拿到业务 JSON）")
    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = [a for a in sys.argv[1:] if a.startswith("--")]
    dry = "--dry-run" in opts
    if not args:
        # 无参数 = 交互式向导：问手机号 → 选参数来源 → 发码 → 输验证码 → 登录 → 验收
        def _int_opt(name, default):
            for o in opts:
                if o.startswith(name + "="):
                    try:
                        return int(o.split("=", 1)[1])
                    except ValueError:
                        return default
            return default
        return cmd_interactive(dry_run=dry,
                               wait=_int_opt("--wait", 40),
                               rounds=_int_opt("--solve-rounds", 6))

    backend, imp, wait = "auto", "chrome", 40
    pf, session_file, code = "captcha_param.json", "session.json", None
    solve_rounds, reuse_fresh = 6, 0
    for o in opts:
        if o.startswith("--backend="):
            backend = o.split("=", 1)[1]
        elif o.startswith("--imp="):
            imp = o.split("=", 1)[1]
        elif o.startswith("--wait="):
            wait = int(o.split("=", 1)[1])
        elif o.startswith("--param="):
            pf = o.split("=", 1)[1]
        elif o.startswith("--session="):
            session_file = o.split("=", 1)[1]
        elif o.startswith("--code="):
            code = o.split("=", 1)[1]
        elif o.startswith("--solve-rounds="):
            solve_rounds = int(o.split("=", 1)[1])
        elif o.startswith("--reuse="):
            reuse_fresh = int(o.split("=", 1)[1])

    use_cookies = "--nocookie" not in opts
    export = next((o.split("=", 1)[1] for o in opts if o.startswith("--export=")), None)

    # status / token 只读 session.json，不依赖 cookies.json
    if args[0] == "status":
        return cmd_status(session_file)
    if args[0] == "token":
        return cmd_token(session_file, export=export, refresh="--refresh" in opts)

    d = load_cookies(ignore_cookies=("--nocookie" in opts))
    n_cookie = len(d.get("cookies") or {})
    print("cookie: %s | UA=%s… | site sid=%s" % (
        ("%d 个" % n_cookie) if n_cookie else "无（不影响 WAF 放行）",
        (d.get("env") or {}).get("ua", "")[:34],
        d.get("site_sso_user_id")))
    if args[0] == "probe":
        return cmd_probe(d, backend, imp, use_cookies)
    if args[0] == "send" and len(args) >= 2:
        return cmd_send(d, args[1], wait, "--solve" in opts, pf, "--no-cool" in opts, backend, imp,
                        use_cookies, dry_run=dry, solve_rounds=solve_rounds, reuse_fresh=reuse_fresh)
    if args[0] == "login" and len(args) >= 2:
        return cmd_login(d, args[1], code, pf, session_file, backend, imp, use_cookies, dry_run=dry)
    if args[0] == "flow" and len(args) >= 2:
        return cmd_flow(d, args[1], wait, "--solve" in opts, pf, "--no-cool" in opts, code,
                        session_file, backend, imp, use_cookies, dry_run=dry,
                        solve_rounds=solve_rounds, reuse_fresh=reuse_fresh)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
