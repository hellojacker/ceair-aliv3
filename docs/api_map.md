# 东航 SSO 登录前端 bundle —— 接口地图（静态分析）

## 0. 分析对象与方法

| 项 | 值 |
| --- | --- |
| 输入文件 | `ceair/site/global-login.bundle.js` |
| SHA-256 | `061C515A6852E887CA205B58BCA353137847C524762E336391E2C402FA0EBC87` |
| 体积 | 889,906 字节 / 870,792 字符（单行压缩，webpack 4 `window.webpackJsonp` 打包） |
| 写入 | 原文件全程只读；派生产物仅写入 `ceair/_sub_api/`，报告仅写本文件 |

**偏移约定**：`@N` = 该字面量在原文中的 **0-based 字符下标**（Python `str.find` 语义，按 UTF-8 解码后的字符计数，非字节）。

**标注约定**：
- **【证据】** = bundle 内可直接引用的静态证据，附 `@偏移` + 原文片段（均 ≤200 字符）。
- **【推断】** = 由证据推导，未经运行时验证。
- **【外部证据】** = 来自 bundle 之外的本机文件（注明来源）。

**派生工具**（`ceair/_sub_api/`）：`01_scan.py` 关键字索引 → `02_ctx.py`/*05_rx.py* 上下文窗口 → `03_dump.py` 区间导出 → `04_mods.py`/`06_off.py`/`08_off2.py`/`10_off3.py`/`11–15_*.py` 偏移定位与复核；全部输出在 `ceair/_sub_api/out/`。

**问题索引**：问题 1 → §2.1/§2.4 + §3；问题 2 → §4；问题 3 → §5；问题 4 → §6；问题 5 → §7；问题 6 → §8。

---

## 1. 结论速览

| 前端入口 | HTTP | 完整 URL | 请求体字段 |
| --- | --- | --- | --- |
| `sendCode(e)` 短信验证码 | POST | `https://sso.ceair.com/mumember/api/sso/get/password/code` | `channelType, salesChannel, captchaVerifyParam, phone, telephoneCode` |
| `tologin(e[, riskObj])` 会员密码/手机动态码登录 | POST | `https://sso.ceair.com/mumember/api/sso/login` | `salesChannel, captchaVerifyParam, account, accountType, pin, telephoneCode?`（+风控二段验证时 `verifyCode, codeDestination`） |
| `checklogin()` 登录态探测 | POST | `…/mumember/api/sso/check/token` | `salesChannel` |
| `getUUID()/isconfirm()` 扫码登录 | POST | `…/mumember/api/sso/qrcode/uuid`、`…/mumember/api/sso/login/isconfirmbyscan` | `salesChannel` / `uuid, salesChannel` |
| `wxlogin()` 微信登录 | POST | `…/mumember/api/sso/login/weChatInit` | `succuessUrl, failUrl`（原文即拼写错误 `succuess`） |
| `btnRiskCode()` 风控验证码 | POST | `…/mumember/api/sso/sendVerifyCode` | `phone|email, telephoneCode` |
| `getCountry()` 国家区号 | POST | `…/mumember/api/memberApi/area/country/info` | `{}`（空对象） |
| `logout()` | POST | `…/mumember/api/sso/logout` | 透传参数 |

成功判定统一为 **`resultCode === "A200"`**（共 10 处，见 §5.1）。

---

## 2. 传输层（先确定，后面所有接口都走这一层）

### 2.1 baseURL 与运行时前缀

**【证据 @133775】**
```
N=window.location.href.includes("k8s.ec")?"//testzh.uat.k8s.ec/":"https://sso.ceair.com/"
```
**【证据 @133884】**
```
F={method:"post",baseURL:"".concat(N,"mumember"),headers:{"Content-Type":"application/json;charset=UTF-8"},data:{},timeout:500,withCredentials:!0,responseType:"json"}
```
**【证据 @133905】** 片段 `mumember`

- 生产 baseURL = **`https://sso.ceair.com/mumember`**；`k8s.ec` 测试域名 = `//testzh.uat.k8s.ec/mumember`。
- **【证据 @1347】** webpack publicPath：`r.p="https://sso.ceair.com/new/";`。**【推断】** 本 bundle 由 `https://sso.ceair.com/new/` 提供，同目录还有分包 `vendors~app`。
- **【证据 @290393】** `VUE_APP_LOGIN_BASE_URL_PREFIX:"https://sso.ceair.com/"`（编译期注入的常量，未参与请求拼接）。

### 2.2 axios 实例与被覆盖的响应转换

**【证据 @134206 / @134248 / @134314】**
```
c.a.defaults.withCredentials=!0;var V=L();function M(e){return new Promise((function(t,i){var o=c.a.create({baseURL:F.baseURL,headers:{},transformResponse:[function(e){}]});
```
- 所有接口共用工厂函数 `M(config)`；`U W Y G J H K D` 全是 `M({url,method:"post",data})` 的薄封装（见 §2.6）。
- `withCredentials:!0` → 请求会携带 `sso.ceair.com` 域下的 Cookie（**跨域登录 URL 不再适用**）。
- `transformResponse:[function(e){}]` 返回 `undefined`，**F 里的 `timeout:500`、`Content-Type: application/json;charset=UTF-8` 均为死配置**（新实例只继承 `baseURL`/空 `headers`/该 `transformResponse`）→ **【推断】** 实际请求无 500ms 超时限制，超时为 axios 默认（不限制）。

### 2.3 响应解析（决定 `resultCode` 从哪来）

**【证据 @135160 / @135208】**
```
o.interceptors.response.use((function(e){return null==e.data?JSON.parse(e.request.responseText):JSON.parse(e.data)})
```
**【推断】** 因 `e.data` 恒为 `undefined`（见上），**成功分支实际执行 `JSON.parse(e.request.responseText)`** —— 即后续 `.then(e=>…)` 里的 `e` 就是服务端原始 JSON 对象，字段 `resultCode / resultMsg / resultContent`。

### 2.4 请求头（全部可确认的自定义头）

| 头 | 值 | 证据 |
| --- | --- | --- |
| `ssoUserId` | 一次性随机 UUID（页面加载生成，`open()` 时刷新） | **【证据 @134422】** `t.headers.ssoUserId=V`；**【证据 @134065】** `function L(){function e(){return(65536*(1+Math.random())|0).toString(16).substring(1)}return e()+e()+"-"+e()+…}`；**【证据 @134206】** `var V=L()`；**【证据 @136034】** `j.$on("initReload",(function(e){V=L()}))` |
| `languageCode` / `currencyCode` | **仅** `/api/sso/logout` 请求带（从 Cookie `i18n_site` 拆 `zh_CNY`） | **【证据 @134565】** `t.headers.languageCode=i[0]\|\|"zh",t.headers.currencyCode=i[1]\|\|"CNY"` 与同段前置条件 `["/api/sso/logout"].some(...)` |
| `Content-Type` | POST/PUT/DELETE 时被强制改写为 `application/json` | **【证据 @134750 @134948】** `"formData"===e.ContentType?(…"application/x-www-form-urlencoded;charset=UTF-8"…):t.headers=Object.assign({},t.headers,{"Content-Type":"application/json"})` |
| `Origin` / `Referer` | **代码中不存在**（全文正则 `Referer\|Origin:` 0 命中） | **【证据】** `rx_hdr.txt matches=0`；**【推断】** 由浏览器自动附加，无自定义值 |
| Cookie | 由 `withCredentials` 自动携带 | 见 §2.2 |

> 注意：`sendCode` / `tologin` / `check/token` / `qrcode/*` / `sendVerifyCode` / `country/info` 均**不带** `languageCode`、`currencyCode`。

### 2.5 请求体序列化

**【推断】** 只覆盖了 `transformResponse`，`transformRequest` 未覆盖 → 普通对象按 axios 默认 `JSON.stringify` 序列化，配合 `Content-Type: application/json`。`qrcode/uuid` 例外：传 `ContentType:"formData"`（**【证据 @136321】** `M({url:"/api/sso/qrcode/uuid",method:"post",ContentType:"formData",data:e})`）→ 走 `O.a.stringify(t.data)`（**证据 @134840**，qs 序列化 + `x-www-form-urlencoded`）。

### 2.6 全部接口封装（同一函数体内连续定义，逐字引用）

**【证据 @135824 … @136584】**（节选）：
```
function D(e){return M({url:"/api/sso/logout",method:"post",data:e})}
var U=function(e){return M({url:"/api/sso/login",method:"post",data:e})},
W=function(e){return M({url:"/api/sso/get/password/code",method:"post",data:e})},
Y=function(e){return M({url:"/api/sso/check/token",method:"post",data:e})},
G=function(e){return M({url:"/api/sso/qrcode/uuid",method:"post",ContentType:"formData",data:e})},
J=function(e){return M({url:"/api/sso/login/isconfirmbyscan",method:"post",data:e})},
H=function(e){return M({url:"/api/sso/login/weChatInit",method:"post",data:e})},
K=function(e){return M({url:"/api/memberApi/area/country/info",method:"post",data:e})
```
| 封装 | URL | `url:` 字面量偏移 | 实际调用点（偏移） |
| --- | --- | --- | --- |
| `U` | `/api/sso/login` | @136096 | `U(a).then(` @196768（`tologin` 内） |
| `W` | `/api/sso/get/password/code` | @136165 | `return W(i)` @193032（`sendCode` 内） |
| `Y` | `/api/sso/check/token` | @136246 | `Y({salesChannel…` @187602（`checklogin`） |
| `G` | `/api/sso/qrcode/uuid` | @136321 | `G({salesChannel…` @193561（`getUUID`） |
| `J` | `/api/sso/login/isconfirmbyscan` | @136419 | `J(t).then(` @194332（`isconfirm`） |
| `H` | `/api/sso/login/weChatInit` | @136504 | `H(t).then(` @186562（`wxlogin`） |
| `K` | `/api/memberApi/area/country/info` | @136584 | `K({}).then(` @185985（`getCountry`） |
| `D` | `/api/sso/logout` | @135824 | `D().then(` @216053（`Je.prototype.logout`） |
| （内联） | `/api/sso/sendVerifyCode` | @173805 | `btnRiskCode`（同函数 @173758 起） |

---

## 3. `sendCode(e)` —— 短信/动态码接口（问题 1）

### 3.1 调用链

**【证据 @191866】** 阿里云验证码回调 → 分发：
```
AliyunCaptchaDoFunction:function(e){var t=this;this.showLoading=!0,1==this.mode?this.sendCode(e).then((function(){t.captchaVerifyParam=e})):0==this.mode&&this.tologin(e)}
```
**【证据 @192438】** 按钮点击（`获取验证码`）先做本地校验再弹验证码：
```
handleSendCode:function(){""!=this.form.phonenum.trim()?this.checkNum(this.form.phonenum)?this.captcha.show():this.setRuleMessage({name:"phonenum"},!0,this.$t("login.message.RightNum")):…}
```
→ 即「获取验证码」按钮点击 → `captcha.show()`（阿里云弹窗）→ 用户通过 → `success(captchaVerifyParam)` → `sendCode(captchaVerifyParam)`。
（模板侧证据 **@207232**：`o("div",{staticClass:"global-login-sendcode",…,on:{click:e.handleSendCode},…})`）

### 3.2 完整请求（逐字）

**【证据 @192853】**
```
sendCode:function(e){var t=this,i={channelType:"CN",salesChannel:"en"==this.langShort?"7696":"7690",captchaVerifyParam:e,phone:this.form.phonenum,telephoneCode:this.country.code};return W(i).then(…
```

| 项 | 值 | 证据 |
| --- | --- | --- |
| 完整 URL | `https://sso.ceair.com/mumember/api/sso/get/password/code` | 组合 @133884（baseURL）+ @136165（url）|
| 方法 | `POST` | **【证据 @136165】** `method:"post"` |
| Content-Type | `application/json` | **【证据 @134948】** |
| `channelType` | 硬编码 `"CN"` | **【证据 @192888】** `channelType:"CN"` |
| `salesChannel` | `langShort==="en" ? "7696" : "7690"` | **【证据 @192905】** |
| `captchaVerifyParam` | 阿里云 SDK `success` 回调原样传入的 base64 串（**不解析、不解码**） | **【证据 @192953】**；全文 `certifyId`/`sceneId`/`isSign` 命中数均为 **0** |
| `phone` | 手机号输入框 `this.form.phonenum`（**未做去空格处理**） | **【证据 @192953】** 取 `this.form.phonenum`；对比 `checkNum` 内部 `e=e.replace(/\s+/g,"")`（@188869）|
| `telephoneCode` | 国家区号，默认 `"86"` | **【证据 @192999】** `telephoneCode:this.country.code`；默认值 **【证据 @183294】** `country:{code:"86",extraCode:"CHN",name:"中国",nc:"CN",pinyin:"Z"}` |

> `this.form` 初值 **【证据 @182100】** `form:{account:"",pin:"",phonenum:"",code:""}`。

### 3.3 响应处理（逐字）

**【证据 @193079 / @193189 / @193148】**
```
t.showLoading=!1,"A200"===e.resultCode?(t.isseedcode=!0,t.Interval(),B({message:t.$t("login.message.Note"),time:1e3})):t.popup?t.setRuleMessage({name:"phonenum"},!0,e.resultMsg):B({message:e.resultMsg,time:1e3})})).catch((function(){}))
```
- 成功：`resultCode==="A200"` → 启动 60s 倒计时 + toast「短信发送成功，请注意查收！」（i18n `login.message.Note`）。
- 失败：弹窗模式 → 错误显示在**手机号输入框**下（`setRuleMessage{name:"phonenum"}`，文案 = 服务端 `resultMsg`）；非弹窗模式 → 顶部 toast（同样 `resultMsg`）。
- `.catch(function(){})` **静默吞掉网络异常**（无提示）。

---

## 4. `tologin(e, riskObj)` —— 登录接口（问题 2）

### 4.1 完整请求（逐字）

**【证据 @196226】**
```
tologin:function(e,t){var i=this,o=1<arguments.length&&void 0!==t?t:{},a={salesChannel:"en"==this.langShort?"7696":"7690",captchaVerifyParam:e};return 0==this.mode?a=Object.assign({},a,{account:this.form.account,accountType:"FFP",pin:this.RSAencrypt(this.form.pin,this.publicKey)}):1==this.mode&&(a=Object.assign({},a,{account:this.form.phonenum,accountType:"MOBILE",pin:this.RSAencrypt(this.form.code,this.publicKey),telephoneCode:this.country.code})),o&&o.code&&(a=Object.assign({},a,{verifyCode:o.code,codeDestination:o.codeDestination})),U(a).then(…
```

| 项 | 值 | 证据 |
| --- | --- | --- |
| 完整 URL | `https://sso.ceair.com/mumember/api/sso/login` | @133884 + @136096 |
| 方法 | `POST` | **【证据 @136096】** `method:"post"` |
| `salesChannel` | `"7696"`（en）/ `"7690"`（其它） | **【证据 @196300】** |
| `captchaVerifyParam` | **恒定出现在 body 里**（第 1 个入参；风控二段验证时传空串 `""`） | **【证据 @196348】** 首字段；**【证据 @185178】** `riskLogin:function(e){this.tologin("",e)}` |
| `account` | 模式 0：`this.form.account`（会员卡号/证件号/邮箱/登录名）；模式 1：`this.form.phonenum` | **【证据 @196412】** 段 |
| `accountType` | `"FFP"`（会员密码登录）/ `"MOBILE"`（手机动态码登录） | 同上 |
| `pin` | **RSA 加密后的字符串**：`RSAencrypt(明文, publicKey)`；模式 0 加密 `form.pin`（密码），模式 1 加密 `form.code`（短信动态码） | **【证据 @187354】** `RSAencrypt:function(e,t){var i=new de.a;return i.setPublicKey(t),i.encrypt(e)}`；**【证据 @484324/@484352】** 库为 JSEncrypt `t.version="3.0.0-rc.1"`、`window.JSEncrypt=gt` → PKCS#1 v1.5 + base64 **【推断】** |
| `telephoneCode` | 仅 `accountType=MOBILE` 时带，默认 `"86"` | **【证据 @196644】** |
| `verifyCode` / `codeDestination` | 仅风控二段验证时追加（`resultCode="14"` 打开的高风险弹窗回填）；`codeDestination` = 手机号或邮箱 | **【证据 @196713】** `o&&o.code&&(a=Object.assign({},a,{verifyCode:o.code,codeDestination:o.codeDestination}))`；来源 **【证据 @175364】** `var t={code:i.getRiskFormModel().verifyCode,codeDestination:"phone"===i.riskWay?i.riskFormPhone.phonenum:i.riskFormEmail.email};i.$emit("riskLogin",t)` |

**RSA 公钥（2048-bit，PKCS#8 SPKI，base64）【证据 @147053】**：
```
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqLmyqJ6IEzP6lWOsQrJc3KWERH89l/qtzwt9ws1UJrN/j6o/rsAkYs+mSBCxTI9HhGMNkKpklycYGxUg0Qr4lF+V5sK4oe5BvrTQamdjqphBLHqtRPgp1pXMUT/uNnLwhitxcGhxowoFscmlu2zmjh1EtLhTdz2GhZrcVFbyV2FeRGCpUfNrxAgRms8V6GDT7GA5JZfG2ALveX+UANHab7UWF6XBKIQa+k1IgDvltSOiftWu1+3oIfieZSYsAmCgovuxvDduI0cpNoIf1Q40p9p9HPCd/4ud9V44nOfv5TXzoi90w9RcDQr6dRpSB2b0B+wRqa5aFD5654Oph/WDiwIDAQAB
```
（长度 392 字符 = 294 字节 DER。**【证据 @147049】** `be="MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A…"`，`publicKey:be` @182605。）

### 4.2 触发路径（决定 `captchaVerifyParam` 是否有值）

| 场景 | 触发 | 传入的 `captchaVerifyParam` |
| --- | --- | --- |
| 会员密码登录（`mode=0`） | `handleSubmit` → `this.captcha.show()` → 通过 → `tologin(验证码串)` | 阿里云当次返回的串 |
| 手机动态码登录（`mode=1`） | `handleSubmit` → `this.tologin(this.captchaVerifyParam)` | **复用之前 `sendCode` 那次验证留下的串；若本次会话没点过「获取验证码」，则为初始值 `""`** |
| 风控二段验证 | 高风险弹窗 `$emit("riskLogin", t)` → `riskLogin` → `tologin("", t)` | **显式空串 `""`** |

**【证据 @192037】** `handleSubmit:function(){…if(!this.validate())return;0==this.mode?this.captcha.show():1==this.mode&&this.tologin(this.captchaVerifyParam)…}`
**【证据 @192306】** `this.tologin(this.captchaVerifyParam)`
**【证据 @182568】** 初始值 `captchaVerifyParam:""`
**【证据 @191980】** `t.captchaVerifyParam=e`（在 `sendCode` 的 `.then` 里才赋值）
**【证据 @185178】** `riskLogin:function(e){this.tologin("",e)}`

→ **因此请求体中出现 `captchaVerifyParam: ""` 是完全合法的前端行为（证据级结论），前端不阻止这种请求。**

---

## 5. 响应判定与错误码 / 错误文案（问题 3）

### 5.1 成功判定

**【证据】** 全文 `"A200"` 共 10 处，**全部**用于 `e.resultCode` 严格比较，无第二种成功标识（无 `code`/`success`/`resCode` 判定）：
`@173871`（sendVerifyCode）、`@186011`（country/info）、`@186602`（weChatInit）、`@187693`（check/token）、`@193079`（sendCode）、`@193649`（qrcode/uuid）、`@194358`（isconfirmbyscan）、`@196811`（**login**）、`@216075`、`@216234`（logout）。
形如 **【证据 @196811】** `if(i.showLoading=!1,"A200"!==e.resultCode){…` —— 即 `resultCode` 恒为字符串，`"A200"` 唯一成功码。

### 5.2 `tologin` 失败分支（逐字，重点）

**【证据 @196842】**
```
if("A200"!==e.resultCode){var t=["10150114","10150115","10150116","14","15"],o=e.resultCode||"",a=e.resultMsg;…
```
**【证据 @196962】** `console.log("customCodeToast.indexOf(resultCode)…`
**【证据 @197420】** `if("14"===o)return void i.$refs.highRisk.initData(e.resultContent);`
**【证据 @197528】** `if("15"===o)return void(i.$refs.highRisk.appCheckoutDialogComponent=!0)`
**【证据 @197559】** `else 0==i.mode?i.setRuleMessage({name:"account"},!0,e.resultMsg):1==i.mode&&i.setRuleMessage({name:"phonenum"},!0,e.resultMsg)`
**【证据 @197686】** `else i.callback(e),i.setCookiePinType(e.resultContent.passwordType)`

| `resultCode` | 前端行为 | 按钮/文案 |
| --- | --- | --- |
| `A200` | 登录成功：`callback(e)`（跳转/回调宿主） + 写 Cookie `pinType = resultContent.passwordType`（7 天） | **【证据 @193300】** `setCookiePinType` |
| `10150114` | 弹窗：`content = resultMsg`，确认按钮 `login.content.resetPassword`「重置密码」，取消为空 | @197308 |
| `10150115` | 弹窗：确认 `login.content.retrievepassword`「找回密码」、取消 `login.content.iknow`「知道了」 | @197055 |
| `10150116` | 弹窗：确认 `login.content.revise`「立即修改」，取消为空 | @197199 |
| `14` | `highRisk.initData(e.resultContent)` —— 打开高风险二次身份验证组件（手机号/邮箱 + 验证码） | @197420 |
| `15` | `highRisk.appCheckoutDialogComponent = !0` —— 提示去东航 APP 完成身份认证 | @197528 |
| 其它任意码 | 字段级错误：模式 0 显示在 `account` 下、模式 1 显示在 `phonenum` 下，文案 = 服务端 `resultMsg` | @197559 |

**关键观察【证据】**：**bundle 内不存在任何 captcha 专属错误码**（无「验证码校验失败 / 滑块」类常量；`captcha|captchaVerify` 相关字符串共 26 处，全部为 `captchaVerifyParam` 传参、组件 id、SDK 初始化与 SDK 脚本 URL，见 `out/rx_captcha_all.txt` 偏移表）。**【推断】** 因此验证码类失败只能以「任意 `resultCode` + 服务端 `resultMsg`」的形式回到前端，落在「其它码 → 字段级错误」这一条兜底分支上。

### 5.3 其它接口的失败文案

- `sendCode`：失败 → 字段/ toast，文案 `resultMsg`（@193189）。
- 扫码 `isconfirm`：**【证据 @194643】** `"-100"==t.resultCode?e.scanSuccessTxt=t.resultMsg:…` → 扫码专有错误码 **`-100`**（文案 = `resultMsg`，展示在二维码下方）。
- `checklogin`：失败无提示，仅 `showLoading=!1`。
- `btnRiskCode`：**【证据 @173871】** `"A200"===t.resultCode&&(e.showRiskCode=!0,e.showBackBtn=!0,e.riskInterval()),B({message:t.resultMsg,time:1e3})` → **无论成功失败都 toast `resultMsg`**。
- 风控表单本地文案 **【证据 @174465】** `B({message:"请输入手机号",time:1e3})` / 同类 `"请输入邮箱号"`；邮箱校验 **【证据 @173572】** `i(new Error("请输入有效的邮箱地址"))`。

### 5.4 HTTP 层错误（axios 错误拦截器，逐字）

**【证据 @135470 … @135680】**
```
switch(e.response.status){case 400:e.message="请求错误";break;case 401:break;case 403:e.message="拒绝访问";break;case 404:e.message="请求地址出错: ".concat(e.response.config.url);break;case 408:e.message="请求超时";break;case 500:e.message="服务器内部错误";break;case 501:e.message="服务未实现";break;case 502:e.message="网关错误";break;case 503:e.message="服务不可用";break;case 504:e.message="网关超时";break;case 505:e.message="HTTP版本不受支持"}return B({message:"ERROR: ".concat(e),time:1e3}),Promise.reject(e)
```
→ 注意 **`401` 分支为空**（不改写 message），且最终 toast 的是 `"ERROR: " + [object Object]`（**证据 @135678**，实际是 `Error` 对象字符串化）。

### 5.5 i18n 错误文案常量（三种语言，节选原文）

**【证据 @229855（webpack 模块 `d78f` @229580 起）】** 简体中文包：
```
"message":{"NotEmpty":"不为空!","UserNameLen":"请输入正确的用户名，长度为9到20位!","PSDLen":"密码长度为8到15位!","RightNum":"请输入正确的手机号码！","Note":"短信发送成功，请注意查收！","wxerr":"系统繁忙，请稍后再试","userError":"用户名错误","hasCheckPrivayErr":"请先阅读并同意相关政策"}
```
**【证据 @54661（模块 `40ea`，繁體）、@1583（模块 `"0149"`，English）、@8137（`0735` fr）…】** 同套 key 的其它语言包共 10 个（`out/packs.txt`）：`"NotEmpty"`/`"RightNum"`/`"Note"`/`"PSDLen"` 一一对应；另有
`"verifyTitle":"验证码发送至："`、`"riskCode":"请输入验证码"`、`"riskPhone":"请输入手机号"`、`"retrievepassword":"找回密码"`、`"revise":"立即修改"`、`"resetPassword":"重置密码"`、`"firstLogin":"先登录"`、`"goVerify":"去验证"`、`"forYourSecurity":"为了保障您的账户安全，请前往东航APP身份认证后再使用该功能。"`。
**`login.message.UserNameLen` 在代码中 0 命中**（只在语言包里定义）→ **【证据】** 前端未做登录名长度校验。

### 5.6 toast 组件与 3s 自动关闭

**【证据 @133665 / @133759】** `k.install=function(e)…e.prototype.$toastMessage=k;var B=k`；**【证据 @132627】** `function k(e){…`；**【证据 @132964】** 内部 `…},3e3)`（3 秒自动关闭）。

---

## 6. 关键问题：服务端先校验 `captchaVerifyParam` 还是先校验手机号/账号密码？（问题 4）

**结论：从 bundle 只能证明「两个请求都把 `captchaVerifyParam` 与业务字段放在同一个 JSON body 里一起提交」，服务端内部判定顺序属于推断。**

### 6.1 证据链（事实）

| # | 事实 | 证据 |
| --- | --- | --- |
| E1 | `captchaVerifyParam` 是**不透明 base64 串**，前端只读转发，从不解析：全文 `certifyId`/`sceneId`/`isSign` 命中 **0** | 【证据】`offsets.txt` 第 63–65 行 `NOT FOUND`；`captchaVerifyParam` 仅 5 处：@182568 初始化、@191982 赋值、@192324 传入 `sendCode` 的实参、@192953 sendCode body、@196348 tologin body |
| E2 | 字段**顺序**上 `captchaVerifyParam` 排在业务字段之前（`salesChannel, captchaVerifyParam, account/pin…` / `channelType, salesChannel, captchaVerifyParam, phone, telephoneCode`） | 【证据 @196226 / @192853】 |
| E3 | 前端**没有**任何 captcha 失败码/文案分支，所有验证码失败只能落到兜底分支 | 【证据】§5.2、`out/rx_captcha_all.txt` |
| E4 | 前端允许发出 `captchaVerifyParam:""` 的请求（风控二段验证、未点过「获取验证码」直接登录） | 【证据 @185178 / @182568】 |
| E5 | 短信模式下，`sendCode`（发短信）**必须**先过阿里云验证码才被调用（前端顺序） | 【证据 @191866 / @192438】 |
| E6 | 密码模式下，同样的验证码串在同一个请求里与账号密码同时提交，无二次校验请求 | 【证据 @196226】，且全文仅 2 处登录请求封装（U=login） |

### 6.2 推断

- **推断 A（较强）**：服务端在 `/api/sso/login` 与 `/api/sso/get/password/code` 内部**先校验验证码、再校验手机号/账号密码**。理由：E3+E4 —— 如果验证码校验在后，前端必然能观察到「验证码无效」与「账号/密码错误」两类不同反馈；而 bundle 中不存在任何验证码类错误分支，说明服务端对验证码失败也走通用 `resultCode/resultMsg` 兜底通道，前端无法区分顺序。**这是推断，不是证据。**
- **推断 B（较强）**：`captchaVerifyParam` **可被复用/为空时由服务端决定是否放行**。依据 E4：风控二段验证路径显式传空串并复用同一条 `U(login)` 接口，说明服务端对空串有独立分支（例如风控场景豁免或强校验）。**推断。**
- **推断 C（弱）**：短信接口与登录接口可能共用同一验证码校验中间件（两个 body 的验证码字段名完全一致，且都伴随 `salesChannel`）。**推断。**
- **未知**：验证码在服务端是否一次性消费（同一串能否重复用于 `sendCode` 与 `tologin`）——bundle 未体现，需动态抓包/重放验证。

### 6.3 建议的动态验证实验（若需要把推断升级为证据）

1. 固定手机号，用**同一个** `captchaVerifyParam` 依次请求 `get/password/code` 与 `login`，观察第二次返回码（一次性 / 可复用）。
2. 用**伪造 base64**（`base64({"certifyId":"x","sceneId":"10hhki73","isSign":true})`）请求 `login`：若返回「账号不存在/密码错误」→ 验证码非先校验；若返回通用错误码 → 先校验。
3. 用空 `captchaVerifyParam` 请求 `login`（不触发风控），观察是「验证码为空」类 `resultMsg` 还是业务错误。

---

## 7. 前端提前校验（会把请求挡在本地）（问题 5）

### 7.1 隐私政策勾选闸门

**【证据 @192037 / @192355 / @183214】**
```
handleSubmit:function(){if(this.isCheckPrivay){…}else this.hasCheckPrivay=!0}
```
`isCheckPrivay:!1,hasCheckPrivay:!1` 初值 @183214；`wxlogin` 同样被该开关拦（@186820）。
→ **未勾选「隐私政策」时，既不弹验证码也不发请求。**

### 7.2 表单校验（`validate()`）

**【证据 @189974】**
```
validate:function(){var e=this,t=[],i=[];return 0==this.mode?t=["account","pin"]:1==this.mode&&(t=["phonenum","code"]),…!t.some((function(t){return 1==e.rules[t].showerr}))}
```
**【证据 @189596 / @189696】** 逐字段规则：
```
case"account":""==e.value.trim()&&this.setRuleMessage(e,!0,this.$t("login.message.NotEmpty"))
case"pin":(e.value.length<8||15<e.value.length)&&this.setRuleMessage(e,!0,this.$t("login.message.PSDLen"))
case"phonenum":this.checkNum(e.value)||this.setRuleMessage(e,!0,this.$t("login.message.RightNum"))
```
| 字段 | 本地规则 | 挡住请求？ |
| --- | --- | --- |
| `account`（会员号/登录名） | **仅非空**（长度 9–20 的校验只在语言包里，代码 0 命中） | 空 → 挡 |
| `pin`（密码，模式 0） | 长度 **8–15**，否则 `login.message.PSDLen` | 是 |
| `phonenum` | `checkNum` 正则 | 是 |
| `code`（短信动态码，模式 1） | 仅非空 | 空 → 挡 |
| `captchaVerifyParam` | **无任何校验** | 不挡 |

### 7.3 手机号正则（原文逐字）

**【证据 @188869】**
```
checkNum:function(e){return"86"===this.country.code?(e=e.replace(/\s+/g,""),/^1[3456789]\d{9}$/.test(e)):/^[0-9][0-9]{0,14}$/.test(e)}
```
- 中国大陆（`telephoneCode==="86"`）：`/^1[3456789]\d{9}$/`，**先去掉所有空白**（`\s+` 替换为空）；注意第 2 位**只允许 3–9**（`190/191/192/193/194` 号段会被本地拦下）。
- 其它国家/地区：`/^[0-9][0-9]{0,14}$/`（1–15 位纯数字）。
- 仅覆盖 `handleChange`（失焦/输入）与 `handleSendCode`；**登录提交时 `phone` 用的是未去空格的 `this.form.phonenum`**（**【证据 @192953】**）→ 带空格可能被发到服务端（**【推断】** 由此产生的差异只能由服务端处理）。

### 7.4 60 秒频控（仅 UI 层）

**【证据 @182485】** `second:60,isseedcode:!1`；**【证据 @192701/@192732】** `Interval:function(){var e=this;this.timer=setInterval((function(){e.second--,0===e.second&&(e.second=60,e.isseedcode=!1,clearInterval(e.timer))}),1e3)}`；**【证据 @193079】** 成功后 `t.isseedcode=!0,t.Interval()`。
模板 **【证据 @206940 / @207232】**
```
e.isseedcode?o("div",{staticClass:"global-login-sendcode-active",…},[e._v(…e.$t("login.content.sentAgain")+"("+e.second+")")…]):o("div",{staticClass:"global-login-sendcode",…,on:{click:e.handleSendCode},…})
```
→ 倒计时期间该按钮被**替换成不可点击的 div**（`global-login-sendcode-active`），**没有**本地时间戳/次数限制；三处 60s 计时器：短信 `@192732`、扫码 `qrcodeoverdue` `@193947`、风控验证码 `@172506`（`checkSecond:60`）。

### 7.5 其它

- `showLoading` 仅控制 loading 遮罩，**不拦截提交**（**【证据 @191866】** 一路 `this.showLoading=!0`）。
- 登录按钮模板 **【证据 @209639】** `handleSubmit` 第二处（模板绑定）。

---

## 8. 其它常量（问题 6）

| 常量 | 值 | 证据 |
| --- | --- | --- |
| `salesChannel` | `langShort==="en" ? "7696" : "7690"`（共 5 处：check/token @187605、getUUID @193564、isconfirm @194283、sendCode @192905、tologin @196300） | **【证据 @192905】** |
| `langShort` 来源 | `this.lang.split("_")[0]`，缺省 `"zh"` → `zh_CN/zh_TW → "7690"`；`en_US → "7696"` | **【证据 @184557】** `langShort:function(){return this.lang?this.lang.split("_")[0]:"zh"}`；**【证据 @172533】** 风控组件同款 |
| `channelType` | 硬编码 `"CN"`（仅 `sendCode` 使用，全文 1 处） | **【证据 @192888】** |
| `telephoneCode` 默认 | `"86"`（`country.code`，来自 `data()` 初值或 `/api/memberApi/area/country/info` 选择） | **【证据 @183294 / @171719】** `country:{code:"86",extraCode:"CHN",name:"中国",nc:"CN",pinyin:"Z"}` |
| 阿里云验证码 SceneId | `"10hhki73"` | **【证据 @146702】** `window.initAliyunCaptcha({SceneId:"10hhki73",mode:"popup",element:"#captcha-element",…})` |
| 验证码语言 | `zh→"cn"`、`hk→"tw"`、其它原样（`en`） | **【证据 @146559】** `getLang:function(){var e=this.langShort;return"zh"===e?"cn":"hk"===e?"tw":e}` |
| 滑块的 slideStyle | `{width:360,height:40}` | **【证据 @147004】** |
| 成功后自动重初始化 | `success` 回调里 `setTimeout(()=>this.initAliyunCaptcha(),500)`（每次验证通过后 500ms 重新 init） | **【证据 @146782（success 回调）/ @146879（setTimeout 500）】** |
| SDK 配置脚本 | `https://www.ceair.com/global/static/commonlib/AliyunCaptchaConfig/index.js` | **【证据 @214002】** |
| SDK 主脚本 | `https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js`（注入条件 `!window.AliyunCaptchaConfig` @213890） | **【证据 @214145 / @213890】** |
| SDK 实例引用 | `getInstance:function(t){e.captcha=t}` → `this.captcha.show()` 触发弹窗 | **【证据 @146967 / @192272】** |
| 阿里云 region / prefix | `region:'cn'`、`prefix:"pxb8fg"` | **【外部证据】** `ceair/AliyunCaptchaConfig.js`（该 URL 的本地副本，非 bundle 内容） |
| `#captcha-element` 归属 | bundle 模板内只有 `<div id="global-login-captcha" style="display:none">`（@211268），`#captcha-element` 在**宿主页面** | **【证据 @211268】** + **【外部证据】** `ceair/recon4_login_dialog.html` 含 `<div id="captcha-element"></div>` |
| RSA 公钥 / 库 | JSEncrypt 3.0.0-rc.1，2048-bit | **【证据 @147053 / @484324】** |
| 事件埋点 `gio` | `gio("track","eventHappen",…)`、`gio("setUserId",…)`、`gio("clearUserId")` —— 无网络请求代码（由外部 SDK 处理） | **【证据 @186898 / @198061】** |

---

## 9. 侧链：宿主集成与其它网络行为

- 对外 API：**`window.GlobalLogin`**（`Je` 类），**【证据 @215877】** `Je.prototype.open=function(){return j.$emit("tkshow",!0),j.$emit("initReload"),this}`；**【证据 @215943】** `…j.$emit("option",JSON.stringify(this.option))`；**【证据 @215676 附近】** `Je.prototype.setoption` / `close` / `logout`。
- 宿主页面通过 `option` 传入运行参数（`isOverSea`、`lang`、`redirectUrl` 等）→ **【证据 @213333】** `o.isOverSea=!!o.isOverSea&&o.isOverSea`（宿主 JSON 解析分支）；`lang` 决定 `salesChannel`（§8）。
- 跳转白名单：**【证据 @185220】** `sanitizeRedirectUrl:function(e){…return["javascript:","data:","vbscript:","file:"].some((function(e){return t.includes(e)}))}`；`getRedirectUrl` 只放行含 `ceair.com` 的 URL，否则回落 `https://www.ceair.com/`。
- 登录成功后的跳转：**【证据 @198287】** `window.location.replace(decodeURIComponent(t))`，并写 Cookie `redirectUrl`、`pinType`。
- 埋点：**【证据 @186898】** `gio("track","eventHappen",…`；**【证据 @198061】** `gio("setUserId",e.resultContent.userId)`；`gio("clearUserId")`。
- 全文绝对 URL 清单（27 条，含 SDK/条款/跳转页）见 `ceair/_sub_api/out/urls.txt`。

---

## 10. 干扰项（避免误读）

**【证据 @131173】** 同一 bundle 内另有 vuex 模块 `y={namespaced:!0,state:{userInfo:{…},loginForm:{username:"",password:"",captcha:""},…}}`，其 `actions.login` 是**假实现**：
```
setTimeout((function(){o("setUserInfo",{username:i.username,token:"mock-token",isLoggedIn:!0}),…}),1e3)
```
（**【证据 @131800 起】**）—— 其中的 `captcha` 字段**不是**阿里云验证码，**不代表任何接口**。该 store 已挂到 `new m.a.Store({…})`（**【证据 @133193】** `…,modules:{login:y}}`）。

---

## 11. 可复现请求样例（占位符）

> 说明：以下仅是把 §3/§4 的证据字段按 HTTP 形式写出，用于本地/沙箱联调；`CAPTCHA_B64` 需由阿里云 SDK（SceneId `10hhki73`）真实产出，`PIN_ENC` 需用 §4.1 公钥 + JSEncrypt 生成。

```bash
# 1) 短信验证码
curl -sS 'https://sso.ceair.com/mumember/api/sso/get/password/code' \
  -H 'Content-Type: application/json' \
  -H 'ssoUserId: 8a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9' \
  --data-raw '{"channelType":"CN","salesChannel":"7690","captchaVerifyParam":"CAPTCHA_B64","phone":"PHONE","telephoneCode":"86"}'

# 2) 会员密码登录（mode=0）
curl -sS 'https://sso.ceair.com/mumember/api/sso/login' \
  -H 'Content-Type: application/json' \
  -H 'ssoUserId: 8a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9' \
  --data-raw '{"salesChannel":"7690","captchaVerifyParam":"CAPTCHA_B64","account":"FFP_ACCOUNT","accountType":"FFP","pin":"PIN_ENC"}'

# 3) 手机动态码登录（mode=1）
curl -sS 'https://sso.ceair.com/mumember/api/sso/login' \
  -H 'Content-Type: application/json' \
  --data-raw '{"salesChannel":"7690","captchaVerifyParam":"CAPTCHA_B64","account":"PHONE","accountType":"MOBILE","pin":"SMSCODE_ENC","telephoneCode":"86"}'

# 4) 风控二段验证（captchaVerifyParam 为空串，证据 @185178）
curl -sS 'https://sso.ceair.com/mumember/api/sso/login' \
  -H 'Content-Type: application/json' \
  --data-raw '{"salesChannel":"7690","captchaVerifyParam":"","account":"FFP_ACCOUNT","accountType":"FFP","pin":"PIN_ENC","verifyCode":"VERIFY_CODE","codeDestination":"PHONE_OR_EMAIL"}'
```

响应判定：`json.resultCode === "A200"` → 成功；否则读 `resultMsg`（服务端文案），并按 §5.2 的码表分支。

---

## 12. 尚未闭环的未知项

1. `captchaVerifyParam` 在服务端是否一次性消费（§6.3 实验 1）。
2. 服务端对**空串** `captchaVerifyParam` 的处理分支（风控豁免？强校验？）— 只能动态验证。
3. `resultContent` 的完整字段（仅见 `passwordType`、`userId`、`accountType`、`onlyRelateOneFfpAccount`、`skipAccountRelate`、`isScan/isScanExpire/isLogin`、`weChatRedirectUrl` 等被引用字段，**未穷举**）。
4. 服务端 `pin` 解密与 RSA 填充方式（PKCS#1 v1.5 为**【推断】**，由 JSEncrypt 默认行为与 `publicKey` 推断）。
5. 同目录分包 `vendors~app`（**【证据 @1521 / @262832】**）未纳入本次分析范围；如需要可另取该 chunk 复核是否还有登录相关请求（当前证据：登录请求封装全部在本文件，**【推断】**不存在第二处定义）。

---

### 附：中间产物索引（`ceair/_sub_api/`）

| 文件 | 内容 |
| --- | --- |
| `01_scan.py` / `out/scan.txt` | 55 个关键字全量命中索引（含偏移与片段） |
| `02_ctx.py` / `out/ctx_core.txt` `ctx_codes.txt` `ctx_urls.txt` `ctx_rules.txt` `ctx_zh.txt` `ctx_risk.txt` | 合并窗口的上下文阅读视图 |
| `03_dump.py` / `out/dump_*.txt` | `tologin_full`（@195820-201600）、`wrappers`（@134600-141200）、`reqfn`、`store`、`captcha_ui` 等原始区间 |
| `04_mods.py` / `out/mods_urls.txt` | 全部 `url:"…"` 字面量与 `/api/...` 路径 |
| `05_rx.py` / `out/rx_*.txt` | 正则取证：`codes`、`a200`、`sales`、`aliyun`、`mode`、`branch`、`hdr`、`captcha_all`… |
| `06_off.py` `08_off2.py` `10_off3.py` / `out/offsets*.txt` | 报告中引用的全部锚点偏移表 |
| `07_urls.py` / `out/urls.txt` | bundle 内 27 条绝对 URL |
| `09_final.py` / `out/final.txt` | RSA 公钥全文、`form` 初值、模块号 |
| `11_verify.py` `13_verify2.py` `14_check.py` `15_verify3.py` / `out/verify.txt` `check.txt` | 报告中每个引用的偏移复核（每一项都跑过一遍再写入本文件） |
| `12_packs.py` / `out/packs.txt` | i18n 语言包 → webpack 模块号映射（10 个语言） |
