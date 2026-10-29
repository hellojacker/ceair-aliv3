# -*- coding: utf-8 -*-
"""页面钩子：让 iv8 里的 SDK 能"看到"真实由 Python 拉回来的资源。

负责三件事：
1. 拦截 script.src / link.href 赋值，记录 SDK 动态想要的 FeiLin、pe.0XX.js、main.css；
2. 同 realm eval 注入脚本，并按 SDK 的 `function(t){ t ? 失败 : 成功 }` 语义**无参**触发 load；
3. 轨迹明文侧录（JSON.stringify / TextEncoder.encode 命中 xPos、TrackList 时留档）。
"""

HOOKS_JS = r"""
(function(){
  window.__S = {wanted: [], css: [], served: [], notes: [], pending: {}};
  // 轨迹明文插桩：只在内容命中 xPos/TrackList 时记录（不改 SDK 源码）；独立数组避免自引用
  window.__PLAIN = [];
  try {
    var ojs = JSON.stringify;
    JSON.stringify = function(){
      var s = ojs.apply(this, arguments);
      try { if (typeof s === 'string' && s.length > 20 && s.length < 300000 &&
                 (s.indexOf('xPos') >= 0 || s.indexOf('TrackList') >= 0)) window.__PLAIN.push(s.slice(0, 8000)); } catch(e){}
      return s;
    };
  } catch(e){}
  try {
    if (window.TextEncoder) {
      var oenc = TextEncoder.prototype.encode;
      TextEncoder.prototype.encode = function(){
        try { var a = arguments[0], t = (typeof a === 'string') ? a : '';
              if (t && t.length > 20 && (t.indexOf('xPos') >= 0 || t.indexOf('TrackList') >= 0)) window.__PLAIN.push(t.slice(0, 8000)); } catch(e){}
        return oenc.apply(this, arguments);
      };
    }
  } catch(e){}
  var RES = /captcha-frontend\/(FeiLin|dynamicJS)/;
  function note(url, el, kind){
    var u = String(url);
    if (!RES.test(u)) return;
    if (!window.__S.pending[u]) window.__S.pending[u] = [];
    if (el) window.__S.pending[u].push(el);
    (kind === 'css' ? window.__S.css : window.__S.wanted).push(u);
  }
  var ds = Object.getOwnPropertyDescriptor(HTMLScriptElement.prototype, 'src');
  if (ds && ds.set){
    Object.defineProperty(HTMLScriptElement.prototype, 'src', {
      configurable: true,
      get: function(){ return ds.get.call(this); },
      set: function(v){ this.__iv8Url = String(v); note(v, this, 'js'); try{ ds.set.call(this, String(v)); }catch(e){} }
    });
  }
  try {
    var dl = Object.getOwnPropertyDescriptor(HTMLLinkElement.prototype, 'href');
    if (dl && dl.set){
      Object.defineProperty(HTMLLinkElement.prototype, 'href', {
        configurable: true,
        get: function(){ return dl.get.call(this); },
        set: function(v){ this.__iv8Url = String(v); note(v, this, 'css'); try{ dl.set.call(this, String(v)); }catch(e){} }
      });
    }
  } catch(e){}
  var ap = Node.prototype.appendChild;
  Node.prototype.appendChild = function(node){
    var r = ap.apply(this, arguments);
    try {
      if (node && node.tagName === 'SCRIPT') note(node.src || node.__iv8Url || '', node, 'js');
      if (node && node.tagName === 'LINK') note(node.href || node.__iv8Url || '', node, 'css');
    } catch(e){}
    return r;
  };
  // SDK 回调签名是 function(t){ t ? 失败 : 成功 } —— 成功必须**无参**触发
  function fireLoad(node){
    var fired = false;
    try { if (typeof node.onload === 'function'){ node.onload(); fired = true; } } catch(e){}
    try { if (typeof node.onreadystatechange === 'function'){ node.readyState = 'complete'; node.onreadystatechange(); fired = true; } } catch(e){}
    try { node.dispatchEvent(new Event('load')); fired = true; } catch(e){}
    return fired;
  }
  window.__serveScript = function(url, src){
    var ok = true, err = null;
    try { (0, eval)(src); } catch(e){ ok = false; err = String(e).slice(0, 400); }
    window.__S.served.push({url: String(url).slice(0, 110), ok: ok, err: err});
    var els = window.__S.pending[url] || [], fired = 0;
    for (var i = 0; i < els.length; i++){ if (fireLoad(els[i])) fired++; }
    if (!fired){
      var nodes = document.querySelectorAll('script');
      for (var j = 0; j < nodes.length; j++){
        var u = String(nodes[j].src || nodes[j].__iv8Url || '');
        if (u === url) fired += fireLoad(nodes[j]) ? 1 : 0;
      }
    }
    return JSON.stringify({ok: ok, err: err, fired: fired});
  };
  window.__serveCss = function(url){
    var els = window.__S.pending[url] || [], fired = 0;
    for (var i = 0; i < els.length; i++){ if (fireLoad(els[i])) fired++; }
    if (!fired){
      var nodes = document.querySelectorAll('link');
      for (var j = 0; j < nodes.length; j++){
        var h = String(nodes[j].href || nodes[j].__iv8Url || '');
        if (h === url) fired += fireLoad(nodes[j]) ? 1 : 0;
      }
    }
    return 'css-fired:' + fired;
  };
  window.__SDump = function(){ return JSON.parse(JSON.stringify(window.__S)); };
  return 'hooks-ready';
})()
"""

