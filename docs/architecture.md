# 架构与流程（ceair 滑块求解器）

> 这份文档回答三个问题：**代码怎么分层**、**一次求解到底发生了什么**、**要改某件事该动哪个文件**。
> 图用 Mermaid 写，GitHub / VS Code / Typora 可直接渲染。

## 1. 分层原则

1. **配置 / 逻辑 / 文案分离**：站点常量、浏览器画像、几何映射全在 `solver/config.py`；注入 JS 全是纯字符串（`solver/js/`），不含 Python 逻辑；流程代码只调用、不硬编码。
2. **协议顺序在 `solve.py` 一处可见**：从 `page.load` 到收割参数是固定顺序，读一个函数就能看完整个协议，不用跨文件拼。
3. **入口不动**：`ceair_solver.py` / `gap2.py` 保留为兼容门面，既有命令与 `tools/` 的 `import` 全部照旧。
4. **等价优先于"更优雅"**：`detect_gap`（生产）与 `gap2.solve`（诊断）数学同源但故意不合并——两者边界处理不同，合并会改变已标定的求解结果。

## 2. 模块划分

| 文件 | 职责 | 不该放什么 |
|---|---|---|
| `ceair_solver.py` | **兼容门面**：重导出公共 API + `__main__` | 任何实现 |
| `gap2.py` | **诊断门面**：`gap2.solve` 离线看打分表 + `__main__` | 任何实现 |
| `solver/config.py` | 站点配置（URL/SceneId/prefix/region）、UA、浏览器画像 `MACHINE`（通用默认值，CEAIR_* 可覆盖）、几何映射 `MAPPING_A/B`、偏移与缩放、SDK 源码、壳页 HTML | 流程控制 |
| `solver/env.py` | 把画像拼成 iv8 的 `environment`（location/navigator/document/window/screen） | 判定、计算 |
| `solver/js/patches.py` | iv8 能力补丁：`MessageChannel` 端口、`TextEncoderStream` 段错误规避 | 站点相关逻辑 |
| `solver/js/hooks.py` | 页面钩子：捕获动态 script/link、同 realm eval 注入、**无参**触发 load、轨迹明文侧录 | Python 侧判断 |
| `solver/js/init.py` | `initAliyunCaptcha` 参数模板（默认不挂 `captchaVerifyCallback`） | 网络 |
| `solver/js/drag.py` | 人类式拖动：缓入曲线 + 微调闭环 + 收尾驻留 | 缺口识别 |
| `solver/gap.py` | 缺口识别 `detect_gap`（生产）/ `solve`（诊断）/ `inverse_mapping`（xPos→位移反解） | 网络、DOM |
| `solver/bridge.py` | `netLog` ↔ 真实 HTTP 的四步握手；落盘 `back.png`/`shadow.png`；记录 `InitCaptchaV3`/`VerifyCaptchaV3` 原文 | 判定逻辑 |
| `solver/solve.py` | 一次求解的主流程（顺序即协议） | 参数解析 |
| `solver/cli.py` | 参数解析、轮次重试、`VerifyCode` 判定、产物落盘 | 协议细节 |

### 依赖关系

```mermaid
graph TD
    subgraph 入口
        CS["ceair_solver.py<br/>（门面）"]
        G2["gap2.py<br/>（门面）"]
        MAIN["solver/cli.py<br/>main()"]
    end
    subgraph 核心
        SOLVE["solver/solve.py<br/>solve_once()"]
        BRIDGE["solver/bridge.py<br/>Bridge"]
        GAP["solver/gap.py<br/>detect_gap / solve"]
        ENV["solver/env.py<br/>build_env()"]
        CFG["solver/config.py<br/>常量 / 画像 / 映射"]
        subgraph JS["solver/js/（纯字符串）"]
            P["patches.py"]
            H["hooks.py"]
            I["init.py"]
            D["drag.py"]
        end
    end
    subgraph 运行时
        IV8["iv8（C++ V8 + 浏览器环境）"]
        NET["真实 HTTP<br/>requests / curl_cffi"]
        SITE["www.ceair.com<br/>阿里云验证码 v3"]
    end

    CS --> SOLVE
    CS --> GAP
    CS --> MAIN
    G2 --> GAP
    MAIN --> SOLVE
    SOLVE --> BRIDGE
    SOLVE --> GAP
    SOLVE --> ENV
    SOLVE --> P & H & I & D
    BRIDGE --> CFG
    SOLVE --> CFG
    GAP --> CFG
    ENV --> CFG
    SOLVE --> IV8
    BRIDGE --> NET
    NET --> SITE
```

## 3. 一次求解的完整时序

```mermaid
sequenceDiagram
    autonumber
    participant CLI as solver/cli.py
    participant S as solver/solve.py
    participant V8 as iv8 (JSContext)
    participant B as solver/bridge.py
    participant N as 真实网络
    participant SITE as ceair / 阿里云验证码

    CLI->>S: solve_once(with_callback, time_mode)
    S->>V8: JSContext(environment=build_env(), mode="prod", time_mode="system")
    S->>V8: __iv8__.page.load(壳页 HTML)
    S->>V8: eval(PATCH_JS) → MessageChannel 补丁
    S->>V8: eval(PATCH_STREAMS) → TextEncoderStream polyfill
    S->>V8: eval(HOOKS_JS) → 劫持 script/link 赋值 + __serveScript/__serveCss
    S->>V8: eval(SDK_JS, name="AliyunCaptcha.js") → 定义 initAliyunCaptcha
    S->>V8: eval(INIT_JS) → initAliyunCaptcha({SceneId, mode:popup, success/fail})

    loop 最多 24 轮 pump，直到拼图渲染
        V8-->>B: netLog.entries（Log1 / InitCaptchaV3 / 动态 JS / 图片）
        B->>N: 按 URL 发真实请求（UA/Origin/Referer）
        N->>SITE: HTTPS
        SITE-->>N: 响应（JSON / PNG）
        N-->>B: 响应体
        B->>V8: add_resource(url, body) 回填
        B->>B: 落盘 back.png / shadow.png；记录 InitCaptchaV3 原文
        V8-->>B: __SDump()：SDK 想要的 FeiLin / pe.0XX.js / main.css
        B->>V8: eval 脚本源码（同 realm）+ __serveScript(无参触发 load)
    end

    S->>S: detect_gap(back.png, shadow.png) → x_png
    S->>S: hole = x_png + 2；target = hole × 300/296 − 2；s_est = inverse_mapping(target)
    S->>V8: eval(DRAG_JS) → 缓入拖动 + ≤4 次微调 + 驻留后 mouseup
    V8->>SITE: SDK 自行 POST VerifyCaptchaV3（带轨迹 deviceToken）
    SITE-->>V8: Result{VerifyCode, securityToken}
    B->>B: 截获 VerifyCaptchaV3 请求/响应原文
    S->>V8: 收割 __probe.success / __probe.param / __sd.trace / __PLAIN
    S-->>CLI: out（successDecoded 含 securityToken）+ netlog
    CLI->>CLI: VerifyCode == "T001" ? 命中则停 : 继续下一轮
    CLI->>CLI: 落盘 captcha_param.json / captcha_success.json / captcha_netlog.json
```

## 4. 判决与重试

```mermaid
flowchart TD
    A[求解一轮] --> B{VerifyCode}
    B -->|T001| C[通过：securityToken 有效]
    B -->|F001| D[行为分/轨迹被判异常]
    B -->|F015| E[缺口位置偏差]
    D -->|"重跑（轨迹随机）"| A
    E -->|"重跑（自动换题）"| A
    C --> F[写 captcha_param.json 等产物]
    F --> G[1 分钟内提交 sendCode]
```

> 实测：`T001` 通常 1–3 轮内出现；`F001`/`F015` 属**判决结果**而非程序异常，`--until-t001=N` 会自动重试。

## 5. 提交与登录链路（`submit_requests.py`）

```mermaid
flowchart TD
    subgraph WAF["传输层"]
        P1["probe<br/>POST check/token"] -->|200| P2["WAF 放行<br/>（curl_cffi chrome 指纹）"]
    end
    subgraph SEND["发码"]
        S1["send / flow &lt;手机号&gt;"] --> S2["captchaVerifyParam<br/>（T001 的 success）"]
        S2 --> S3["POST /mumember/api/sso/get/password/code<br/>Site: zh_CN"]
        S3 -->|A200| S4["短信真实下发"]
        S3 -->|A500| S5["频率限制 / 缺 Site 头"]
        S3 -->|"code=6"| S6["captchaVerifyParam 无效/过期"]
    end
    subgraph LOGIN["登录（已实现）"]
        L0["人工输入 6 位短信码"] --> L1["pin = RSA_PKCS1_v1_5(码)<br/>344 字符 base64"]
        L1 --> L2["POST /mumember/api/sso/login<br/>accountType=MOBILE, telephoneCode=86"]
        L2 -->|A200| L3["Set-Cookie 会话凭证<br/>resultContent{userId,passwordType,…}"]
        L2 -->|"14 / 10150114|115|116"| L4["高风险二段 / 强制改密<br/>脚本只报含义，不代做"]
        L3 --> L5["POST check/token 验收"]
        L5 -->|A200| L6["session.json<br/>cookies + resultContent + tokens"]
        L5 -->|非 A200| L7["登录态不完整（重登）"]
    end
    S4 -.->|"同一 session（cookie 连续）"| L0
```

- **已实测通过（2026-10-18）**：滑块 → `securityToken`、发码 `A200`、WAF 通行、登录（RSA pin）`A200` → `check/token` `A200` → `session.json`（`tokenKey` 与 3 个同值 cookie）。
- 仍自动化不了：读短信（必须人工输入 6 位码）；服务端二段风控（`14`/`15`/`10150114`）只报码不代办。
- 会话形态：凭证以 **cookie** 为主（`session.json` 存全量 cookie + `resultContent` 里命中 `token|ticket|sess|auth` 的字段），`status` 子命令用同一 cookie 复查。

### 登录时序

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant CLI as submit_requests.py
    participant SITE as sso.ceair.com
    U->>CLI: flow <手机号> --solve
    CLI->>CLI: ceair_solver.solve_once() → T001 的 success
    CLI->>SITE: POST get/password/code（captchaVerifyParam=success）
    SITE-->>CLI: A200（短信已发）
    SITE-->>U: 6 位短信码
    U->>CLI: 输入验证码
    CLI->>CLI: pin = RSA_PKCS1_v1_5(code)（344 字符）
    CLI->>SITE: POST login{salesChannel,captchaVerifyParam,account,accountType:MOBILE,pin,telephoneCode:86}
    SITE-->>CLI: A200 + Set-Cookie + resultContent
    CLI->>SITE: POST check/token{salesChannel}
    SITE-->>CLI: A200（登录态有效）
    CLI->>CLI: 写 session.json（cookies / resultContent / tokens）
```

## 6. 要改某件事，动哪个文件

| 需求 | 改这里 | 注意 |
|---|---|---|
| 换目标站 / SceneId / prefix | `solver/config.py` | 同时确认 `SUCCESS` 判定与站点 bundle 的初始化参数 |
| 换浏览器画像（核数/内存/触屏/屏幕/窗口） | `solver/config.py` 的 `MACHINE`，或环境变量 `CEAIR_UA/CORES/MEM/TOUCH/SCREEN/WIN` | 画像改变会影响指纹一致性 |
| 重标定 `xPos ↔ slidePos` | `solver/config.py` 的 `MAPPING_A/B`、`PIECE_CANVAS_OFFSET`、`IMG_DISPLAY_SCALE` | 必须与 `docs/ceair_captcha_report.md` 的几何测量一起更新 |
| 调拖动轨迹（通过率） | `solver/js/drag.py` | 曲线/停顿/微调次数；改完跑 `--until-t001=3` 看命中率 |
| 换缺口识别算法 | `solver/gap.py` 的 `detect_gap`（生产路径） | 不要动 `solve`（诊断），否则历史打分表不可比 |
| 补 iv8 缺失 API | `solver/js/patches.py` | 只补宿主能力，不碰 SDK 源码 |
| 补风控二段 / 其它登录分支 | `submit_requests.py` 的 `cmd_login()`（错误码表） | 现有：MOBILE 动态码；`14` 二段需追加 `verifyCode + codeDestination` |

## 7. 等价性怎么验

重构前后逐项比对，脚本在 `tools/verify_refactor.py`（默认取 `_backup/ceair-*` 里最新的备份）：

```bash
.venv\Scripts\python.exe tools\verify_refactor.py
# 或指定备份： --backup ..\_backup\ceair-20261018-213854
```

核心断言：

1. 17 个模块常量（含 5 段注入 JS）与备份版**逐字节一致**；
2. `build_env()` / `build_env(cookie)` 字典相等；
3. `inverse_mapping()` 在 10 个采样点相等；
4. `detect_gap()` 对 `back.png`/`shadow.png` 输出相同（最近一次：x=178）；
5. `gap2.solve()` 分数表长度与首项相同（178 / 246 项 / 0.462147）；
6. `py_compile` 覆盖 `solver/**` + 门面 + `tools/*.py` 共 87 个文件。

回归另跑真实链路：`python ceair_solver.py --until-t001=3` → 命中 `T001`，`securityToken` 128 字符
（`F015`/`F001` 是缺口偏差/行为分的**判决结果**，属正常重试范围，不是程序异常）。
