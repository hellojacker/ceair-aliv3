# -*- coding: utf-8 -*-
"""注入 iv8 的代码：都是原样字符串，不做任何 Python 侧逻辑处理。

    patches.py  iv8 能力补丁（MessageChannel / TextEncoderStream 段错误规避）
    hooks.py    页面钩子（动态脚本捕获、同 realm 注入、load 事件语义）
    init.py     站点初始化调用（initAliyunCaptcha 参数）
    drag.py     人类式拖动（缓入曲线 + 微调闭环 + 收尾驻留）
"""
