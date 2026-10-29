# -*- coding: utf-8 -*-
"""iv8 浏览器环境画像。

真机采集值（grab_env.py）落在 config.MACHINE；这里只负责把画像包成 iv8 认识的
environment 字典，别在此处做判定或计算。
"""
from .config import MACHINE, PAGE_URL, UA

def build_env(cookie_str=""):
    return {
        "location": {"href": PAGE_URL, "origin": "https://www.ceair.com", "protocol": "https:",
                     "host": "www.ceair.com", "hostname": "www.ceair.com", "port": "",
                     "pathname": "/zh/cny/home", "search": "", "hash": ""},
        "navigator": {"userAgent": UA, "language": "zh-CN", "languages": ["zh-CN", "zh"],
                      "platform": "Win32", "webdriver": False,
                      "hardwareConcurrency": MACHINE["cores"], "deviceMemory": MACHINE["mem"],
                      "maxTouchPoints": MACHINE["touch"], "vendor": "Google Inc.",
                      "productSub": "20030107", "onLine": True, "cookieEnabled": True,
                      "webdriver": False},
        "document": {"title": "机票预订_飞机票查询_东航官网", "URL": PAGE_URL, "referrer": "https://www.ceair.com/",
                     "readyState": "complete", "visibilityState": "visible", "hidden": False,
                     "characterSet": "UTF-8", "cookie": cookie_str},
        "window": {"innerWidth": MACHINE["win"][0], "innerHeight": MACHINE["win"][1],
                   "outerWidth": MACHINE["win"][2], "outerHeight": MACHINE["win"][3],
                   "devicePixelRatio": 1.0, "isSecureContext": True},
        "screen": {"width": MACHINE["screen"][0], "height": MACHINE["screen"][1],
                   "availWidth": MACHINE["screen"][2], "availHeight": MACHINE["screen"][3],
                   "colorDepth": 24, "pixelDepth": 24},
    }

