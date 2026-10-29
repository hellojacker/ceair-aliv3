# ceair-captcha

东航（`www.ceair.com`）登录滑块 —— 阿里云验证码 2.0 v3（`PUZZLE` 拼图）的**纯 Python 离线求解 + 协议提交**实现。

核心思路一句话：**把目标站真实下发的 AliyunCaptcha SDK 原封不动地放进 iv8（C++ V8 + 浏览器环境）里执行**，
用 Python 侧补齐它需要的网络与宿主能力，让 SDK 自己生成 `VerifyCaptchaV3` 请求与 `CaptchaVerifyParam`；
再换 `curl_cffi` 伪装 Chrome TLS 指纹，把发码 / 登录请求走通。

- 不需要 Node，不需要真浏览器（求解路径零浏览器）
- 不修改 SDK 源码：`netLog` 抓请求、`add_resource` 回填响应、同 realm eval 注入动态脚本
- 缺口识别纯 numpy/PIL，无 OpenCV

---

## 1. 目录结构

```
ceair-captcha/
├── ceair_solver.py           # 主入口：离线求解一次，产出 CaptchaVerifyParam（兼容门面）
├── submit_requests.py        # 主入口：纯 Python 提交（发码 / 登录 RSA / 验收 / 取 token）
├── check_env.py              # 环境自检：Python、依赖版本、iv8 引擎、DOM、curl_cffi
├── gap2.py                   # 缺口识别诊断门面（gap2.solve 打印打分表）
├── requirements.txt          # 依赖锁定（Python 3.9）
├── login.cmd                 # Windows 一键：求解 → 发码 → 输码 → 登录 → 验收
├── activate_env.cmd          # 进入项目 venv 的快捷 shell
├── solver/                   # 求解器实现（按职责分层）
│   ├── config.py             #   站点常量 / UA / 浏览器画像 / 几何映射（唯一该改的地方）
│   ├── env.py                #   iv8 浏览器环境画像
│   ├── gap.py                #   缺口识别（生产 detect_gap + 诊断 solve）
│   ├── bridge.py             #   netLog → 真实 HTTP 四步握手桥
│   ├── solve.py              #   一次求解主流程（顺序即协议顺序）
│   ├── cli.py                #   参数 / 轮次重试 / T001 判定 / 产物落盘
│   └── js/                   #   注入 iv8 的纯字符串：patches / hooks / init / drag
├── sdk/
│   └── AliyunCaptcha.js      # 站点真实下发的 SDK 副本（运行时硬依赖，@146702 同源）
└── docs/
    ├── architecture.md       # 分层架构与流程图
    ├── ceair_captcha_report.md  # 逆向过程与结论（协议时序、字段语义）
    ├── api_map.md            # 接口地图（发码 / 登录 / check）与请求体样例
    └── USAGE.md              # 逐条命令与参数说明
```

> `.venv/`、`cookies.json`、`session.json`、`captcha_*.json`、`back.png`、`shadow.png` 都是**本地产物**，
> 已由 `.gitignore` 排除；重建环境即可再生成。
>
> 文档里提到的 `tools/`、`cdp/`、`artifacts/`、`chrome_profile/` 是作者本地的**一次性侦察/取证目录**，
> 不属于可运行链路，**未随本仓库发布**；`docs/` 中保留这些引用只为说明当时的验证方式。
> 浏览器环境画像（核数 / 内存 / 屏幕 / 触摸点）默认是**通用桌面值**，可用 `CEAIR_CORES`、`CEAIR_MEM`、
> `CEAIR_TOUCH`、`CEAIR_SCREEN`、`CEAIR_WIN`、`CEAIR_UA` 环境变量覆盖。

---

## 2. 快速开始

```bash
# 0) 环境（Python 3.9.x，iv8 只有 cp39 wheel）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe check_env.py        # 全 [OK] 再往下
```

```bash
# A) 只解滑块（离线，不开浏览器）
.venv\Scripts\python.exe ceair_solver.py --until-t001=6

# B) 求解 → 发短信 → 手工输码 → 登录 → 验收 → 落 session.json
.venv\Scripts\python.exe submit_requests.py flow 13800138000 --solve --wait=40
#    拆开等价于：
#    ... submit_requests.py send  13800138000 --solve --wait=40
#    ... submit_requests.py login 13800138000
#    ... submit_requests.py status

# C) 只探针（不发短信，确认 WAF 放行）
.venv\Scripts\python.exe submit_requests.py probe
```

Windows 双击 `login.cmd` 等价于 B（会提示输入手机号与验证码）。

---

## 3. 产物

| 文件 | 内容 |
|---|---|
| `captcha_param.json` | `param` / `success` / `verifyCode` / `verifyResponse` / 明文轨迹 / `xPos` / `slidePos` |
| `captcha_success.json` | 细节全量（`trace`、`initResponse`、`verifyRequest`） |
| `captcha_netlog.json` | 网络桥逐条记录（SDK 发了什么、Python 回了什么） |
| `back.png` / `shadow.png` | 本轮背景图与拼图块（供缺口识别复核） |
| `session.json` | 登录后会话与 token（仅本地） |

---

## 4. 关键技术点

1. **SDK 不重写**：`sdk/AliyunCaptcha.js` 原样 `ctx.eval` 进 iv8，`Function.prototype` 与全局对象保持同 realm，
   避免跨 realm 导致的 `instanceof` / 原型链失配。
2. **网络桥**：社区版 iv8 没有真实网络栈，`solver/bridge.py` 读 `netLog.entries` 取出 SDK 想发的请求，
   由 Python 用 `curl_cffi(impersonate="chrome")` 真发，再 `add_resource` 把响应写回虚拟网络。
   覆盖 `InitCaptchaV3` / `VerifyCaptchaV3` 与动态脚本拉取。
3. **动态脚本注入**：SDK 运行时要 `FeiLin`、`pe.0XX.js`、`main.css`，由 Python 抓源码后同 realm eval，
   并按 SDK 的 `function(t){ t ? 失败 : 成功 }` 语义**无参**触发 `onload`。
4. **能力补丁**（`solver/js/patches.py`）：iv8 的 `MessageChannel` 端口是空壳，core-js 调度器一用就崩，
   用纯 JS 重实现；只补宿主缺失能力，不碰 SDK 源码。
5. **几何映射**：iv8 没有 layout 通道，但本 SDK 的拖动几何不依赖 layout，
   实测 `xPos = 0.0035556·s² + 0.07628·s`（`s` = 轨迹位移），与真机逐点一致。
6. **缺口识别**（`solver/gap.py`）：块边界沿 x 滑动，与背景强边缘（Sobel 幅值）对齐打分，取最高分位置。
7. **WAF**：裸 `requests` 会 403；`curl_cffi` 的 Chrome TLS/HTTP2 指纹可直过（带不带宽 cookie 都 200）。

---

## 5. 已知限制

- `iv8` 只有 CPython 3.9 的 wheel，`check_env.py` 会硬校验 `3.9.x`。
- 单轮离线求解成功率约 60%，靠 `--rounds` / `--until-t001` 重试拉稳定。
- 短信验证码需人工输入（本项目不做短信拦截，只用你本人收到的码）。
- 站点换 SceneId / prefix / SDK 版本时，先改 `solver/config.py`，再重新标定 `MAPPING_A/B`。

---

## 6. 说明

代码与文档仅用于**个人学习**：验证码前端逆向、V8 环境补全、TLS 指纹与协议时序分析。
请只在自己有权操作的账号与数据上运行。
