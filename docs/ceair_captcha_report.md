# 东航 www.ceair.com 登录滑块（阿里云验证码 2.0 v3 · PUZZLE 拼图）逆向 + 求解报告

> 目标：`https://www.ceair.com/zh/cny/home` 登录滑块（真实登录页：`https://sso.ceair.com/new/login?type=mobile`）
> 场景：`SceneId=10hhki73`、`prefix=pxb8fg`、`region=cn`、`Mode=popup`、`CaptchaType=PUZZLE`
> 环境：Windows x64 / Python 3.9.13 / iv8 0.1.4 / Chrome 155（真机对账）
> 参考：《逆向分析阿里v3登录滑块》（小张学逆向）、《Ali_V3拼图验证JS逆向IV8纯python环境》（zackaaaaaaa）

---

## 0. 结论一句话

滑块**已完全解决，端到端打通**：

```
python cdp\solve_and_submit.py <手机号>          # 一条命令
   → iv8 纯 Python 离线解出拼图 → VerifyCaptchaV3 得 T001 + securityToken（阿里云判决）
   → 同源提交发码接口（站点 axios 同款头）→ {"resultCode":"A200"} → 短信真实下发
```

实测（本机，多次复现）：离线单轮 T001 通过率 ~60%（带重试稳定通过）；整条链路 30–40s 出 A200。

---

## 0.1 三个曾把人带偏的坑（务必先看）

| 现象 | 真实原因 |
|---|---|
| 提交总回 `code 6 "Authentication failed"` | 参数缺失/无效（例如用了**没有 `securityToken` 的假 success 值**，见 §1 坑 2） |
| 提交总回 `A500 "fail"` | **不是验证码被拒**，而是**频率限制**：同一手机号 30s 内重复发码时后端返回 `A500`，文案为「很抱歉，请30秒后再次尝试获取动态密码。」——等 30–40s 再提交即可 |
| 我们手搓的 fetch 被拒、站点 axios 却能过 | 站点 axios 设了**全局默认头**：`accept: application/json, text/plain, */*`、`accept-language: zh_CN`、**`Site: zh_CN`**。缺 `Site` 头 → 后端判 fail |

```js
// sso app.js 证据（@48280 起 const f = 设置 i18n 时）：
c.a.defaults.headers.common["Accept-Language"] = e;            // e = locale
5 === e.length && (c.a.defaults.headers.common.Site = e);      // "zh_CN" → Site: zh_CN
6 === e.length && (c.a.defaults.headers.common.Languagecode = ..., ...Currencycode = ...);
// @59505 请求拦截器里再补 ssoUserId（页面级复用同一 uuid）
```

---

## 1. 完整发包链路（实测抓包，含关键修正）

```
① Log1(设备指纹) → https://cloudauth-device-dualstack.cn-shanghai.aliyuncs.com/
      ← {"ResultObject":{"DeviceConfig":"…"}}          # AES 可解出 fp_key/session_id/feilin.js/ts/ip
② InitCaptchaV3  → https://pxb8fg.captcha-open.aliyuncs.com/
      AaduaneId=111jdk439dJJIjd023823201 & SignatureMethod=HMAC-SHA1 & SignatureVersion=1.0
      Timestamp=<UTC秒> & Version=2023-03-05 & Action=InitCaptchaV3 & SceneId=10hhki73
      Language=cn & Mode=popup & DeviceToken=<base64 5段> & SignatureNonce=<uuid> & Signature=<HMAC-SHA1>
      ← {"CertifyId":"<10位>","CaptchaType":"PUZZLE","StaticPath":"3.29.0/pe.0XX.<sha>",
         "Image":"qst/PUZZLE/online/891/<uuid>/back.png","PuzzleImage":"…/shadow.png"}
③ 动态 JS/CSS：FeiLin 1.5.2 feilin0XX + dynamicJS/3.29.0/pe.0XX + main.css（**版本每轮轮换，必须运行时解析**）
④ 拼图交互（mousedown/mousemove/mouseup）→ SDK 本地组装轨迹
⑤ ★ VerifyCaptchaV3 → https://<prefix>-VERIFY.captcha-open.aliyuncs.com/     ← 本轮新增的关键一环
      Action=VerifyCaptchaV3 & SceneId & CertifyId & CaptchaVerifyParam=<完整 JSON>
      ← {"Success":true,"Result":{"VerifyCode":"T001","VerifyResult":true,
          "securityToken":"6oOo…","certifyId":"…"}}
⑥ SDK 产出站点侧参数：base64({"certifyId","sceneId":"10hhki73","isSign":true,"securityToken":"…"})
⑦ 站点提交 → POST https://sso.ceair.com/mumember/api/sso/get/password/code
      {"channelType":"CN","salesChannel":"7690","captchaVerifyParam":"<⑥的base64>","phone":…,"telephoneCode":"86"}
      ← {"resultCode":"A200"}        # 通过（短信下发）；失败时为 A500 / code 6
```

**两个必须知道的坑（此前极易误判）**

1. **`-verify` 子域**：验证请求发往 `https://<prefix>-verify.captcha-open.aliyuncs.com/`，
   `VerifyCaptchaV3` 只在「拖动被正确完成」后触发；拖错/合成事件不被接受时**完全没有该请求**，
   看上去就像"客户端不做验证"。
2. **只在没有 `captchaVerifyCallback` 时才会走 ⑤**：站点配置里没有该回调，所以真实链路会发验证包并拿
   `securityToken`；一旦你自己在 `initAliyunCaptcha` 里提供 `captchaVerifyCallback` 并回 `true`，
   SDK 会跳过后端验证直接回调 `success`——**产出没有 securityToken 的假成功值**（这正是早期
   `code 6 "Authentication failed"` 的原因）。

### 1.1 轨迹明文（插桩 `JSON.stringify`/`TextEncoder.encode` 捕获，未改 SDK 源码）

```json
<32hex 校验前缀>{"TrackList":{
  "mc":"<x,y,t, ,0>", "mu":"<x,y,t, ,0>",
  "mp":"x,y,t,0|…",       // mousemove 序列
  "mm":"x,y,t,0|…|x,y,t,1",
  "tc":"","te":"","tmv":"","ks":"","fi":"",
  "startTime":<ms>,"si":"1440,1440,900,1920,200,1040,900,<ratio>,1920"},
 "TrackStartTime":<ms>,"VerifyTime":<ms>,
 "xPos":"243",       // ← 拼图块 CSS left（服务器比对的坐标）
 "slidePos":"251",   // ← 滑块 CSS left
 "arg":"<8字节 base64>"}
```

### 1.2 deviceToken 明文（base64 解开）

```
WEB#<32hex 设备哈希>-h-<签发毫秒时间戳>-<32hex>#h<约 1KB 密文>#<版本号>#<32hex 摘要>
```
实测 1276–1360 字符；**时间戳每轮变化，不可缓存重放**。

---

## 2. 滑块几何模型（本轮核心突破）

真机与 iv8 双路实测，映射为**二次函数**（二阶差分恒定）：

```
xPos = A·s² + B·s          A = 0.0035556,  B = 0.07628
s(鼠标位移) = slidePos ；反解： s = (-B + √(B² + 4A·xPos)) / (2A)
```

| 采样 | s=30 | 60 | 90 | 120 | 150 | 180 | 真机 237 |
|---|---|---|---|---|---|---|---|
| xPos | 5.50 | 17.40 | 35.68 | 60.36 | 91.42 | 128.88 | **217.65**（公式 217.8）|

结论：**iv8 不补 layout 物理量即与真机一致**（该 SDK 的拖动数学只依赖鼠标事件与自身状态）。
反向验证：一旦注入"真机 geometry"补丁让 `offsetWidth=40/300`，映射立刻被放大（150px 拖动直接顶满 260）→
**不该补**。

---

## 3. 缺口识别（纯 numpy + Pillow，无 opencv）

拼图块与缺口形状逐像素一致 ⇒ 用「块边界 ↔ 背景强边缘」对齐打分：

1. `shadow.png`(52×200 RGBA) 取 alpha>8 得掩膜与 bbox（块画布内偏移 x=2）；
2. `back.png`(296×200) 求 Sobel 梯度并归一化（99 分位抗异常）；
3. 块边界沿 x 滑窗，取边界处背景梯度均值最大者 = 缺口左侧（块画布坐标）；
4. 换算到 xPos： `target_xPos = (best_x + 2) · (300/296) − 2`（背景图被拉伸到 300px 容器）。

典型 top-3 分值断层明显（0.42 / 0.37 / 0.35）；分值贴近时建议重开一轮（脚本自动重试）。

---

## 4. iv8 补环境要点（踩坑清单）

| # | 坑 | 修法 |
|---|---|---|
| 1 | `MessageChannel.port1===null` → core-js 调度器崩 | 注入最小端口对（`__iv8__.wrapNative` 保持原生表面） |
| 2 | `TextEncoderStream` 构造即 C++ 段错误(0xC0000005) | 纯 JS polyfill 顶掉 |
| 3 | 社区版无网络栈 | `netLog` 取请求 → Python `requests` 真发 → `add_resource` 注入 → `drain/tick` 推进 |
| 4 | 动态 `<script>` 跨 realm 拿不到 `__ALIYUN_CRYPT`；iv8 不给 `<script>` 发 load | 钩 `HTMLScriptElement.src`/`HTMLLinkElement.href`/`appendChild`，Python 抓源码后**同 realm eval** + 手动无参触发 load |
| 5 | SDK 回调签名 `function(t){ t ? 失败 : 成功 }` | 成功必须**无参**调用 |
| 6 | 只钩 `<script>` 漏 CSS → `INIT_FAIL` | CSS 也要服务（`Le("css",…)` 有超时校验） |
| 7 | **时间语义** | 时间差校验/行为分站点用 `time_mode="system"`；`logical` 模式下轨迹时间戳不真实，直接拉低行为分（实测 F001 显著增多） |
| 8 | `S`/拖动需要真实时间流逝 | pump 循环里放 `time.sleep(0.012)`，让 JS 定时器真正到期 |

---

## 5. 真机链路驱动要点（要拿 A200 必须知道的）

| 事项 | 结论（实测） |
|---|---|
| 登录页 | `https://sso.ceair.com/new/login?type=mobile`（与接口**同源**；在 `www.ceair.com` 上跨域 fetch 会被网关判 `code 6`） |
| 站点组件 | Vue 实例：`document.querySelector('#app').__vue__` → `unity-login`（`vm.captcha` 即验证码实例） |
| 弹窗 | `vm.captcha.show()`（或页面上点「获取验证码」，需先填手机号且 `span.privay-check` 打勾，按钮 `opacity` 从 0.3→1 才可点） |
| **窗口必须在前台** | 否则 Chrome 节流：每次 `Input.dispatchMouseEvent` 耗时 ~5s（前台 ~10ms），拖动会失败/复位 |
| **不要用 `Emulation.setFocusEmulationEnabled`** | 实测它会破坏 SDK 的拖动（可信事件到达元素却不触发）；只用 `Page.bringToFront` |
| 可信输入可用 | `Input.dispatchMouseEvent`（isTrusted=true）能正常拖动；**页内合成事件也能拖**，但会被判"验证失败" |
| 事件语义 | `mousePressed` 用 `button:"left",buttons:1`；拖动中的 `mouseMoved` 用 `button:"none",buttons:1`；`mouseReleased` 用 `button:"left",buttons:0` |

---

## 6. 离线求解器（`ceair_solver.py`）

```
1. iv8 起环境（画像用通用桌面值：Win32 / Chrome UA / 8 核 / 8G / 1920×1080 / Asia/Shanghai，可用 CEAIR_* 环境变量覆盖）
2. 载入 AliyunCaptcha.js + AliyunCaptchaConfig(region=cn,prefix=pxb8fg) + patches + hooks
3. initAliyunCaptcha({SceneId:'10hhki73', mode:'popup', element:'#captcha-element', language:'cn',
                      slideStyle:{360,40}, success/fail/getInstance})   ← **不提供 captchaVerifyCallback**
4. pump：桥接 Log1 → InitCaptchaV3 → 服务 FeiLin/pe.0XX/main.css → 拼图渲染 → inst.show()
5. 缺口识别 → target_xPos → 反解 s
6. 人类式拖动：反应时间(130–290ms) → 32 帧速度曲线(慢起/中快/末减速，含 2 处微停顿) → 读块位置微调(≤4 次) → 驻留后松手
7. SDK 自己发 VerifyCaptchaV3（经由我们的网络桥接真发）→ 取得 T001 + securityToken → 产出 success
8. 若 VerifyCode ≠ T001（F015 位置 / F001 环境）则自动重开一轮（每题 2 秒）
```

实测（本机）：
- 单轮 T001 通过率 ~60%（5 轮样本 3 中）；加"判到 T001 重试"后可稳定拿到通过样本。
- 单轮耗时 **1.5–3.5s**（含真实网络）；`xPos` 落点与缺口目标误差 ≤0.6px。

命令：
```bash
python ceair_solver.py --until-t001=6        # 求解到服务器判 T001，产出 captcha_param.json
python cdp\solve_and_submit.py <手机号>          # 求解 + 立刻同源提交发码接口
```

---

## 7. 服务器判决（三层，务必分清）

| 层 | 判决 | 实测结果 |
|---|---|---|
| ① 阿里云客户端验证 | `VerifyCaptchaV3 → VerifyCode` | 离线/真机都能拿到 **T001** + `securityToken`（离线约 60%/轮，带重试稳定） |
| ② 东航后端 · 发码接口 | `resultCode` | **离线参数 + 站点同款头 ⇒ A200**（短信下发）；缺 `Site` 头 ⇒ `A500 fail`；参数无效 ⇒ `code 6`；**30s 内重复发码 ⇒ `A500` +「请30秒后再次尝试获取动态密码」** |
| ③ 对照实验（已做过的排除项） | — | 手机号、参数形态（base64/完整 JSON）、`ssoUserId`（站点自带/新 uuid）、会话预热、UA/画像对齐、fetch vs XHR —— 都不是判别点；**判别点 = `Site: zh_CN` 头 + 30s 冷却** |

**已彻底修正的早期误判**：曾把 `A500` 当成"阿里云服务端比客户端严、合成设备环境不达标"，
并据此计划做 canvas/webgl 物理量注入——**该结论错误**（A500 是频率限制）。离线 iv8 产物
（合成环境指纹）经站点路径与我们的 fetch 路径均能拿到 A200，**无需**设备环境注入。

---

## 8. 复现步骤

```bash
pip install iv8 requests numpy pillow curl_cffi     # Python 3.9–3.14；全流程无浏览器

# A. 纯离线求解（判到 T001 为止）
python ceair_solver.py --until-t001=6

# B. 一条命令端到端（离线求解 + 冷却 + 纯 Python 提交 → A200）
python submit_requests.py send <手机号> --solve --wait=40
python submit_requests.py probe                      # 只探针，不发短信
```

**WAF 通行结论（实测）**：裸 `requests` 一律 403；`curl_cffi(impersonate="chrome")`
——**带不带 cookie 都返回 200**。也就是说网宿 WAF 只看 TLS/HTTP2 指纹，**不需要浏览器、不需要 cookie**。

可选（仅取证/兜底）：`cdp/start_chrome.py` + `cdp/export_cookies.py`（导 cookie）+ `cdp/solve_and_submit.py`
（CDP 页面内 fetch 提交）；排障用 `tools/sso_trusted.py`、`tools/header_diff2.py`、`tools/param_shape_matrix.py`。
**文件总索引见根目录 `README.md`。**

## 9. 文件清单

| 文件 | 说明 |
|---|---|
| `README.md` | **文件总索引**（分组、备注、状态、本次整理变更） |
| `ceair_solver.py` | **主交付**：iv8 纯 Python 离线求解器（含 VerifyCaptchaV3 判决与 T001 重试） |
| `submit_requests.py` | **主交付**：纯 Python 提交（curl_cffi 伪装 Chrome TLS + 站点全头 + 冷却） |
| `gap2.py` | 缺口识别库（被主脚本与工具 import） |
| `docs/ceair_captcha_report.md` / `docs/USAGE.md` / `docs/api_map.md` | 本报告 / 使用说明 / 站点接口地图（含 RSA 公钥、错误码、原文偏移） |
| `cdp/export_cookies.py` + `cdp/start_chrome.py` + `cdp/solve_and_submit.py` + `cdp/submit_with_site_headers.py` | 可选：导 cookie / 起 CDP Chrome / 页面内 fetch 提交（兜底方案） |
| `tools/`（67 个） | 过程工具：`sso_trusted`（真机全链路取证）、`header_diff2`（同参数双路径头对比）、`param_shape_matrix`（形态矩阵）、`iv8_dyn`（映射标定）、`show_enc`/`traj_stats`（明文与轨迹统计）、`recon1–12`（抓包侦察）等 |
| `sdk/`、`site/` | 三件套 SDK 与站点 bundle 原样留存 |
| `artifacts/`（157 项）、`logs/` | 实验产物/证据（抓包 JSON、页面快照、真机画像与几何、轨迹明文）与运行日志 |

## 10. 边界与注意

- `certifyId`/`securityToken`/`deviceToken` 均为会话绑定且带时间戳，**求解后应尽快使用**（建议 <1 分钟），不可缓存重放。
- `securityToken` 是站点后端能接受的必要字段；**不要提供 `captchaVerifyCallback`**（否则拿到的是没有 securityToken 的假成功值 → `code 6`）。
- **提交必须带 `Site: zh_CN`**（+ `Accept`/`Accept-Language`）并遵守 **30–40s 冷却**，否则会被误判成"验证码失败"。
- 真机驱动务必：`Page.bringToFront` + **禁用** focus 模拟 + 前台可见窗口，否则拖动失败/输入被节流（5s/事件）。
- 离线单轮 T001 约 60%；失败样本多为 `F015`（位置，缺口识别偶发）或 `F001`（行为），**重开一轮即可**（脚本已自动重试）。
- 本文仅做协议/算法层面的可复现研究，未对站点业务数据做任何写入；短信为验证目的真实下发（本人号码）。
