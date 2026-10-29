# -*- coding: utf-8 -*-
"""iv8 ↔ 真实网络的四步握手桥。

社区版 iv8 没有网络栈，这里用三条通道补齐：

    netLog.entries   Python 侧读 SDK 发出的请求（含 InitCaptchaV3 / VerifyCaptchaV3 的 body）
    requests         真正发 HTTP（带站点 UA / Origin / Referer）
    add_resource     把响应回填进 iv8 的虚拟网络，SDK 侧表现为"请求成功"

同时把 back.png / shadow.png 落盘，供缺口识别使用。
"""
import json
import os
import re

import requests

from .config import PAGE_URL, UA

# ─────────────────────────── 网络桥接 & 资源服务 ───────────────────────────
class Bridge(object):
    def __init__(self, ctx, workdir):
        self.ctx = ctx
        self.wd = workdir
        self.sess = requests.Session()
        self.sess.headers.update({"User-Agent": UA, "Origin": "https://www.ceair.com",
                                  "Referer": PAGE_URL, "Accept": "*/*"})
        self.seen_urls = set()
        self.served = set()
        self.log = []
        self.init_resp = ""
        self.verify_resp = ""
        self.verify_req = ""

    def _fetch(self, url):
        try:
            r = self.sess.get(url, timeout=25)
            if r.status_code == 200 and len(r.content) > 100:
                return r
        except Exception as e:
            self.log.append({"url": url, "err": str(e)[:120]})
        return None

    def pump(self, rounds=6, ms=30):
        for _ in range(rounds):
            try:
                self.ctx.eval("__iv8__.eventLoop.drainMicrotasks()")
                self.ctx.eval("__iv8__.eventLoop.tick(%d)" % ms)
            except Exception:
                break
            self.serve_assets()
            self.bridge_net()

    def bridge_net(self):
        try:
            entries = self.ctx.eval("__iv8__.netLog.entries", to_py=True) or []
        except Exception:
            return
        for e in entries:
            if not isinstance(e, dict):
                continue
            url = str(e.get("url") or "")
            if not url or url in self.seen_urls:
                continue
            self.seen_urls.add(url)
            method = str(e.get("method") or "GET").upper()
            body = e.get("body") or e.get("postData") or ""
            try:
                if method == "GET":
                    r = self.sess.get(url, timeout=25)
                else:
                    r = self.sess.request(method, url, data=body.encode() if isinstance(body, str) else body,
                                          timeout=25, headers={"Content-Type":
                                                               "application/x-www-form-urlencoded; charset=UTF-8"})
                ctype = r.headers.get("content-type", "application/json")
                isimg = "image" in ctype
                payload = r.content if isimg else r.text
                self.ctx.add_resource(url, payload, status=r.status_code, headers={"content-type": ctype})
                if url.endswith("back.png"):
                    open(os.path.join(self.wd, "back.png"), "wb").write(r.content)
                if url.endswith("shadow.png"):
                    open(os.path.join(self.wd, "shadow.png"), "wb").write(r.content)
                act = ""
                m = re.search(r"Action=([A-Za-z0-9]+)", str(body))
                if m:
                    act = m.group(1)
                if act == "InitCaptchaV3":
                    self.init_resp = r.text
                elif act == "VerifyCaptchaV3":
                    self.verify_resp = r.text
                    self.verify_req = str(body)
                self.log.append({"url": url, "action": act, "status": r.status_code,
                                 "resp": ("<binary %d>" % len(payload)) if isimg else r.text[:200]})
            except Exception as ex:
                self.log.append({"url": url, "err": str(ex)[:120]})

    def serve_assets(self):
        try:
            d = json.loads(self.ctx.eval("JSON.stringify(window.__SDump())") or "{}")
        except Exception:
            return
        for url in d.get("wanted", []):
            if url in self.served:
                continue
            self.served.add(url)
            r = self._fetch(url)
            if not r:
                print("  !! 动态 JS 拉取失败:", url[-70:])
                continue
            self.ctx.eval("window.__tmpSrc = %s;" % json.dumps(r.text))
            res = self.ctx.eval("(function(){var s=window.__tmpSrc; delete window.__tmpSrc;"
                                " return window.__serveScript(%s, s);})()" % json.dumps(url))
            self.log.append({"asset": url[-60:], "serve": str(res)[:120]})
            print("  动态 JS 注入:", url[-46:], str(res)[:80])
        for url in d.get("css", []):
            if url in self.served:
                continue
            self.served.add(url)
            r = self._fetch(url)
            if not r:
                continue
            try:
                self.ctx.add_resource(url, r.text, status=200, headers={"content-type": "text/css"})
            except Exception:
                pass
            self.ctx.eval("window.__serveCss(%s)" % json.dumps(url))
            print("  动态 CSS 注入:", url[-46:])

