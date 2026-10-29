# 东航登录滑块（阿里云验证码 v3 · 拼图）— 使用说明

> 目标站：`https://www.ceair.com` / 登录页 `https://sso.ceair.com/new/login?type=mobile`
> 全部命令在仓库根目录（`ceair-captcha/`）执行
>
> 说明：文中提到的 `tools/`、`cdp/`、`artifacts/` 属作者本地一次性侦察/取证目录，未随仓库发布；
> 可运行链路只有 `ceair_solver.py` + `solver/` + `submit_requests.py` + `check_env.py` + `gap2.py`。

---

## 0. 一次性准备（不需要浏览器）

> **虚拟环境不入库，需按 `requirements.txt` 自建**（Python 3.9.13 + iv8 0.1.4 + curl_cffi 0.13.0 + requests/numpy/pillow）。
>
> - 从零重建：`python -m venv .venv` 然后 `.venv\Scripts\python.exe -m pip install -r requirements.txt`
> - 进入环境：双击 `activate_env.cmd`（激活后窗口里直接 `python ceair_solver.py ...`）
> - 不激活也行：`.venv\Scripts\python.exe ceair_solver.py --until-t001=1`
> - 环境自检：`.venv\Scripts\python.exe check_env.py`（全部 `[OK]` 且打印"环境就绪"才算可用）

```bash
pip install iv8 requests numpy pillow curl_cffi   # curl_cffi 用于伪装 Chrome TLS 指纹（绕网宿 WAF）
```

**全流程无浏览器**：求解在 iv8 沙箱里，提交用 curl_cffi（Chrome TLS/HTTP2 指纹）——实测**连 cookie 都不需要**。

```
裸 requests                     → 403 Forbidden（WAF 看 TLS/HTTP2 指纹）
curl_cffi(impersonate=chrome)   → 200 + 业务 JSON（带不带 cookie 都一样）
```

> CDP Chrome / `cdp/export_cookies.py` 现在只是**可选**：
> ① 想做真机对照实验（`tools/sso_trusted.py`、`tools/header_diff2.py`）时用；
> ② 万一某天 WAF 加强了、curl_cffi 被拦，退回 CDP 页面内 fetch 方案。
>
> `cookies.json` 同样**可选**：没有该文件时 `submit_requests.py` 自动按无 cookie 运行并打印一行说明，
> 不会中断流程（`probe` / `send` / `login` / `flow` 都照常）。只有想带真机 UA/画像时才去跑 `cdp/export_cookies.py`。

---

## 1. 三种用法

### A. 纯离线求解（只想确认滑块解对了）

```bash
python ceair_solver.py --until-t001=6      # 判到 T001 为止，最多 6 轮
```
输出 `captcha_param.json`（`param` / `success` 含 securityToken / `verifyCode`=T001 / `plaintext` 轨迹明文 / `xPos`、`slidePos`）。
单轮 1.5–6s。**不需要网络以外的任何依赖，也不需要浏览器。**

### B. 一条命令端到端（出 A200，会真发短信）

```bash
python submit_requests.py send 13800138000 --solve --wait=40    # 现解现提交
python submit_requests.py send 13800138000 --no-cool            # 用已有产物立刻提交
python submit_requests.py probe                                  # 探针：只打 check/token，不发短信
```

成功标志：
```
backend: curl_cffi(chrome)-nocookie
sendCode HTTP 200 -> {"resultCode":"A200","resultMsg":"Success", ...}
✅ A200 Success —— 纯 Python（无浏览器）提交成功，短信已发 <手机号>
```

### C. 登录（发码 → 手动输入验证码 → 登录 → 拿 token）

**最省事：双击 `login.cmd`**（或 `python submit_requests.py`，不带参数）。向导会依次问：

1. 手机号（11 位，可带 +86；输 `q` 退出）
2. 滑块参数来源：`1` 现解 / `2` 复用 2 分钟内的 T001 产物 / `3` 直接用现有 `captcha_param.json`

冷却（40s）与求解轮数（6 轮）**不再询问**，直接取默认值；要改就带参数：`login.cmd --wait=0 --solve-rounds=3`。

之后发码 → 提示 `请输入短信收到的验证码` → 输入 6 位 → 自动登录 + 验收。

只预览不发送：`login.cmd --dry-run`（或 `python submit_requests.py --dry-run`）。

登录不再需要浏览器，纯 Python 走完：

```bash
# 0) 先预演：只打印要发的两个请求体，不发短信、不登录
python submit_requests.py flow 13800138000 --dry-run

# 1) 一条龙：求解 → 发码 → 提示输入 → 登录 → check/token 验收 → 写 session.json
python submit_requests.py flow 13800138000 --solve --wait=40

# 2) 验收登录态（用 session.json 里的 cookie 再打一次 check/token）
python submit_requests.py status

# 或者拆开（每步可单独重试）
python submit_requests.py send  13800138000 --solve --wait=40   # 发码（已有 1 分钟内的产物可省 --solve）
python submit_requests.py login 13800138000                     # 提示：请输入短信收到的验证码
```

**耗时构成（实测，`flow` 一条命令）**

| 阶段 | 实测 | 说明 |
|---|---|---|
| 求解一轮 | **3.4–5.3s** | iv8 起环境 → 拉 `pe.0XX.js`/FeiLin → 缺口识别 → 拖动 → 等判决 |
| 求解总时长 | 命中即停，最多 6 轮 | 常见 1–3 轮（4–16s）；一直 `F001/F015` 时才会跑满（≈30s）|
| 冷却 | 40s | 服务端要求同号 ≥30s 不重复发码；用 `--wait=N` 调 |
| 发码 | 0.3–1s | — |

所以**出现"请输入验证码"前通常是 45–90s**。现在这段时间有实时输出：

```
== iv8 离线求解到 T001（单轮约 3–8s，最多 6 轮；每轮末打印判定）==
  [  0.0s] 第 1/6 轮：起 iv8 → 拉动态 JS → 缺口识别 → 拖动 → 等判决…
  [  5.3s] 第 1 轮完成 5.3s：VerifyCode=F015 xPos=220  → 继续
  [  8.6s] 第 2 轮完成 3.4s：VerifyCode=T001 xPos=246  ✅ 命中
  求解阶段共 8.6s
发码前冷却 40s（服务端要求同号 ≥30s 内不重复发码）…
  剩余 35s… 剩余 30s… … 冷却结束，开始发码
```

想更快：

```bash
python submit_requests.py flow <手机号> --solve --reuse=120 --wait=40   # 2 分钟内有新鲜 T001 产物就直接复用，跳过求解
python submit_requests.py flow <手机号> --solve --solve-rounds=3        # 只给 3 轮（失败再重跑）
python submit_requests.py send <手机号> --no-cool                       # 确认 30s 内没发过码时才用
```

登录请求体（`docs/api_map.md` §4）：

```json
{"salesChannel":"7690","captchaVerifyParam":"<T001 的 success>",
 "account":"<手机号>","accountType":"MOBILE","pin":"<RSA_PKCS1_v1_5(短信码) base64>","telephoneCode":"86"}
```

成功标志：

```
  login        HTTP 200 312ms  ct=application/json
     body: {"resultCode":"A200","resultMsg":"Success","resultContent":{...}}
✅ A200 登录成功；resultContent = {...}
=== 登录态验收（check/token） ===
✅ 已登录（check/token A200）
=== 疑似凭证（token / 会话） ===
  userId  … / cookie.xxx  …
已写入 session.json（含会话 cookie，请按凭据对待）
```

要点：

- `pin` 是 **JSEncrypt 等价实现**（`RSAES-PKCS1-v1_5` + base64），长度 344 字符；`--dry-run` 可先看请求体（`pin` 打码）。
- 短信码必须人工输入（脚本读不到你的短信）；`--code=123456` 可跳过交互。
- 失败码会直接标注含义：`14` 高风险二段（需 `verifyCode + codeDestination`）、`10150114|115|116` 强制改密/找回、`A500` 频率限制。
- 登录成功后会话在 cookie 里；`session.json` 同时保存 `cookies`、`resultContent` 与疑似 token 字段，后续请求可直接复用。

> 产物有时效：`certifyId/securityToken` 建议 **求解后 1 分钟内** 提交；同一手机号两次发码间隔 **≥30–40s**；短信码约 5 分钟有效。

### C.0 实测结果（2026-10-18，脱敏）

```
login        HTTP 200 1749ms  {"resultCode":"A200","resultMsg":"Success",
             "resultContent":{"userId":100000000000,"tokenKey":"100000****0000","accountType":"MOBILE",...}}
Set-Cookie 后共 16 个 cookie（含 access_token / ceair.login.token / com.ceair.cesso）
check/token  HTTP 200 139ms   A200，resultContent.phone 回填 → 登录态确认
✅ 已写入 session.json
```

**token 在哪**：`tokenKey = "<userId>-<uuid>"`（49 字符），与 `access_token`、`ceair.login.token`、`com.ceair.cesso` 三个 cookie 同值。

```bash
python submit_requests.py token                    # 打印 tokenKey / 关键 cookie
python submit_requests.py token --export=headers.txt   # 导出可直接用的 Cookie 头
python submit_requests.py token --refresh          # 先刷一次会话再导出
```

### C.0.1 登录后能读什么（只读验证）

```bash
python tools\probe_session.py          # 脱敏输出
python tools\probe_session.py --raw    # 原始 JSON（仅本机看）
```

| 接口 | 成功码 | 说明 |
|---|---|---|
| `sso …/api/sso/check/token` | `A200` | 登录态 |
| `www …/portal/v3/member/newCheckToken` | `U200` | 会员信息（`user`/`accountSummary`/`ecard`）|
| `www …/portal/v3/shopping/version` | `S200` | 公共读对照 |

注意：`portal` 接口要带 `languageCode: zh`、`currencyCode: CNY`；成功码按业务族不同，不能只认 `A200`。

### C.1 登录接口（`POST /mumember/api/sso/login`）怎么验证

分四层，**前一层的通过是后一层的前提**；脚本：`tools/verify_login.py`。

| 层 | 命令 | 证明什么 | 代价 |
|---|---|---|---|
| **L1 体对齐** | `python tools\verify_login.py` | 字段名/顺序/取值与 bundle 的 `tologin()` 一致；`captchaVerifyParam` 原样透传 | 离线 |
| **L2 算法等价** | 同上 | `pin` = RSAES-PKCS1-v1_5 + base64（256 字节 / 344 字符）；临时密钥对往返能解回明文 | 离线 |
| **L2b 与 JSEncrypt 交叉** | 见下 | 站点 JSEncrypt 的默认填充就是 PKCS#1 v1.5（行为验证，不是读文档） | 需 Chrome |
| **L3 通道探针** | `python tools\verify_login.py --probe` | 端点可达 / WAF 放行 / 字段被解析 / 进入业务分支 | 联网 **1 次**，伪造数据 |
| **L4 真实登录** | `python tools\verify_login.py --phone X --code N` | `A200` + `check/token` `A200` + token 落盘 | 联网 + 真实短信码 |

**L3 实测记录（2026-10-18，只发 1 次）**

```
POST https://sso.ceair.com/mumember/api/sso/login
{"salesChannel":"7690","captchaVerifyParam":"","account":"00000000000",
 "accountType":"MOBILE","pin":"<RSA(000000)，344 字符>","telephoneCode":"86"}

HTTP 200 367ms  ct=application/json
{"resultCode":"1",
 "resultMsg":"登录失败：验证码输入错误，还可尝试4次，次数用完后账户将被锁定24小时，请谨慎操作。",
 "resultContent":null,"transactionId":"892fad7f-…"}
```

判读（证据 / 推断分开）：

- **证据**：`200` + `application/json` + 业务 `resultCode` → 端点、WAF、JSON 体解析、业务分流四层都通；不是 403，也不是 HTML。
- **推断（较强）**：返回的是**带失败计数的凭证错误**，而不是加解密/格式错误。若 `pin` 的 RSA 块格式不对，服务端会在解密阶段抛异常并回通用错误（本仓库见过的 `A500 fail`）；能走到"验证码输入错误 + 剩余次数"，说明 `pin` 已被解出并参与比对。
- **另一种读法**："验证码"也可能指阿里云滑块（本次 `captchaVerifyParam` 传的是空串）。要区分，需用**有效 T001 的 success + 故意错的短信码**再打一次，看文案是否仍指向同一个计数。
- **代价（重要）**：该接口有失败计数（本次回"还可尝试 4 次"），**不要在真实账号上反复试**；正式登录务必一次到位：`flow` 一条命令走完。

**L2b：与站点 JSEncrypt 做行为级交叉验证**（可选，需要登录页）

```powershell
# 1) 生成测试密钥对，拿公钥 B64
.venv\Scripts\python.exe -c "from Crypto.PublicKey import RSA; import base64; k=RSA.generate(2048); open('_test_priv.pem','w').write(k.export_key().decode()); print(base64.b64encode(k.publickey().export_key(format='DER')).decode())"

# 2) 在登录页控制台（cdp/start_chrome.py 打开的那页）执行，粘贴上一步输出的公钥
#    const e = new JSEncrypt(); e.setPublicKey("<TEST_PUB_B64>"); window.__c = e.encrypt("123456"); __c

# 3) 把密文带回 Python，用测试私钥解，应得 123456
.venv\Scripts\python.exe -c "from Crypto.PublicKey import RSA; from Crypto.Cipher import PKCS1_v1_5; import base64,sys; k=RSA.import_key(open('_test_priv.pem').read()); print(PKCS1_v1_5.new(k).decrypt(base64.b64decode(sys.argv[1]), b'FAIL').decode())" "<上一步的密文>"
```

RSA 填充含随机数，同一明文每次密文都不同，所以"等价"只能这样验，不能靠"两次密文相等"。

---

## 2. 关键参数说明

| 参数 | 含义 | 默认 |
|---|---|---|
| `--until-t001=N` | 判到 `T001` 就停，最多 N 轮 | 1（=只跑一次）|
| `--rounds=N` | 固定跑 N 轮 | 1 |
| `--with-callback` | 给 SDK 提供 `captchaVerifyCallback`（**会跳过后端验证、拿不到 securityToken，仅调试用**）| 关 |
| `--wait=N` | 提交前冷却等待秒数 | 35（solve_and_submit）/ 40（submit_with_site_headers）|
| `--no-submit` | 只求解不提交 | — |
| `CEAIR_UA` / `CEAIR_CORES` / `CEAIR_MEM` / `CEAIR_TOUCH` / `CEAIR_SCREEN` / `CEAIR_WIN` | 覆盖 iv8 画像（默认通用桌面值：8 核 / 8G / 非触屏 / 1920×1080，不含本机信息）| — |

---

## 3. 常见问题排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 纯 Python 提交回 **403 Forbidden** | 网宿 WAF 看 **TLS/HTTP2 指纹**，裸 `requests` 过不去 | 用默认的 `curl_cffi`（脚本已内置，`--backend=curl`）；cookie 不是必需项，403 与有没有 cookie 无关 |
| `{"resultCode":"A500","resultMsg":"很抱歉，请30秒后再次尝试获取动态密码。"}` | **频率限制**（同号短时间多次发码）| 等 40s 再提交（`--wait=45`）|
| `{"resultCode":"A500","resultMsg":"fail"}` | 缺站点自定义头 **`Site: zh_CN`** | 用 `submit_requests.py` / `cdp/solve_and_submit.py`（已内置）|
| `{"resultCode":"6","resultMsg":"Authentication failed."}` | `captchaVerifyParam` 无效（常见：用了没有 `securityToken` 的假 success，或参数过期）| 重新求解到 `T001` 再提交；别加 `--with-callback` |
| `VerifyCode=F015` | 缺口识别偶发偏差（位置不对）| 重跑（脚本 `--until-t001` 会自动换题）|
| `VerifyCode=F001` | 行为分/轨迹被判异常 | 重跑；确认没跑在 `--with-callback` 模式 |
| 真机拖动不动 / 输入每次耗时 5s | Chrome 窗口在后台被节流 | `python cdp\start_chrome.py` 后把窗口置前；**不要**用 `Emulation.setFocusEmulationEnabled`（会破坏拖动）|
| `!! 需要先打开 sso 登录页` | 用的是 CDP 方案但没有 Chrome/标签页 | 先 `python cdp\start_chrome.py`；或改用 `submit_requests.py` 纯 Python 方案 |
| `!! 缺少 cookies.json` | **不是错误**：`cookies.json` 可选，没有就自动无 cookie 运行 | 想带真机画像再跑 `python cdp\export_cookies.py`；不跑也能过 WAF |
| 杀软报 `.venv\...\Crypto\Protocol\__pycache__\KDF.cpython-39.pyc` | 第三方杀软对 pycryptodome 预编译 pyc 的启发式误报 | 已改纯 Python RSA，主链不再生成该文件；仍有残留就删 `Crypto` 下 `__pycache__`，或给 `.venv` 加白名单 |
| 求解释放动态 JS 报 `no js source` | 网络取不到 `pe.0XX.js`/FeiLin | 重试；或检查代理/网络 |

---

## 4. 原理速览（详见 `docs/ceair_captcha_report.md`，文件总索引见根目录 `README.md`）

```
Log1(设备指纹) → InitCaptchaV3(拿 certifyId + 拼图 back.png/shadow.png + 动态 pe.0XX.js)
  → 拼图交互（轨迹）→ VerifyCaptchaV3（https://pxb8fg-verify.captcha-open.aliyuncs.com/）
  → T001 + securityToken → success = base64({"certifyId","sceneId":"10hhki73","isSign":true,"securityToken"})
  → 站点 POST /mumember/api/sso/get/password/code → A200
```

- 滑块几何：`xPos = 0.0035556·s² + 0.07628·s`（`s` = 鼠标位移 = `slidePos`），反解即得拖动距离。
- 缺口识别：拼图块边界 ↔ 背景强边缘对齐打分（纯 numpy，无需 opencv）。
- iv8 补环境要点：MessageChannel 端口对、TextEncoderStream polyfill、动态脚本**同 realm eval** + 无参触发 load、CSS 也要服务、`time_mode="system"`。
- 提交三要素：`Site: zh_CN` 头 + `ssoUserId` + 30–40s 冷却。

---

## 5. 注意

- 短信是**真实下发**到目标手机号；测试请用自己的号码，并控制频率。
- 本文与脚本仅做协议/算法层面的可复现研究，未对站点业务数据做任何写入。
