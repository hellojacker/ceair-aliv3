# -*- coding: utf-8 -*-
"""iv8 0.1.4 能力补丁。

- MessageChannel：iv8 的端口是 null 空壳，SDK 的 core-js 调度器一用就崩 → 纯 JS 重实现。
- TextEncoderStream：构造即 C++ 段错误（0xC0000005）→ 用纯 JS 顶掉。
两者都不碰 SDK 源码，只补宿主缺失能力。
"""

PATCH_JS = r"""
(function(){
  var Native = window.__iv8__ && window.__iv8__.wrapNative;
  function wrap(fn, name){ return Native ? Native(fn, name) : fn; }
  // iv8 0.1.4 的 MessageChannel 端口是 null 空壳，SDK 的 core-js 调度器会直接崩
  function makePatch(){
    function Port(){ this.onmessage = null; this._peer = null; this._listeners = []; }
    Port.prototype.postMessage = wrap(function(data){
      var self = this;
      setTimeout(function(){
        var peer = self._peer; if (!peer) return;
        var ev = {data: data, type: 'message', ports: [], target: peer, origin: ''};
        if (typeof peer.onmessage === 'function') { try { peer.onmessage(ev); } catch(e){} }
        var ls = peer._listeners.slice(0);
        for (var i = 0; i < ls.length; i++) { try { ls[i](ev); } catch(e2){} }
      }, 0);
    }, 'postMessage');
    Port.prototype.addEventListener = wrap(function(type, fn){
      if (type === 'message' && typeof fn === 'function') this._listeners.push(fn);
    }, 'addEventListener');
    Port.prototype.removeEventListener = wrap(function(type, fn){
      var i = this._listeners.indexOf(fn); if (i >= 0) this._listeners.splice(i, 1);
    }, 'removeEventListener');
    Port.prototype.dispatchEvent = wrap(function(){ return true; }, 'dispatchEvent');
    Port.prototype.start = wrap(function(){}, 'start');
    Port.prototype.close = wrap(function(){}, 'close');
    function MessageChannel(){
      var p1 = new Port(), p2 = new Port();
      p1._peer = p2; p2._peer = p1; this.port1 = p1; this.port2 = p2;
    }
    try { Object.defineProperty(MessageChannel, 'name', {value:'MessageChannel', configurable:true}); } catch(e){}
    window.MessageChannel = MessageChannel;
    return typeof window.MessageChannel;
  }
  return JSON.stringify({messageChannel: makePatch()});
})()
"""

PATCH_STREAMS = r"""
(function(){
  // iv8 0.1.4 的 TextEncoderStream 构造时会 C++ 段错误（0xC0000005），用纯 JS 顶掉
  function TextEncoderStream(){
    if (!(this instanceof TextEncoderStream)) throw new TypeError("Failed to construct 'TextEncoderStream'");
    var enc = new TextEncoder(), queue = [], readers = [], closed = false;
    function push(chunk){ if (readers.length) readers.shift()(Promise.resolve({value: chunk, done: false})); else queue.push(chunk); }
    function finish(){ closed = true; while (readers.length) readers.shift()(Promise.resolve({value: undefined, done: true})); }
    this.writable = { locked:false, highWaterMark:1, getWriter:function(){ return {
      desiredSize:1, ready:Promise.resolve(), closed:Promise.resolve(),
      write:function(chunk){ var u8 = (chunk && chunk.buffer) ? chunk : enc.encode(String(chunk)); push(u8); return Promise.resolve(); },
      close:function(){ finish(); return Promise.resolve(); },
      abort:function(){ finish(); return Promise.resolve(); }, releaseLock:function(){} }; },
      abort:function(){ finish(); return Promise.resolve(); }, close:function(){ finish(); return Promise.resolve(); } };
    this.readable = { locked:false, getReader:function(){ return {
      read:function(){ if (queue.length) return Promise.resolve({value: queue.shift(), done:false});
                       if (closed) return Promise.resolve({value: undefined, done:true});
                       return new Promise(function(res){ readers.push(res); }); },
      cancel:function(){ finish(); return Promise.resolve(); }, releaseLock:function(){}, closed:Promise.resolve() }; },
      cancel:function(){ finish(); return Promise.resolve(); }, pipeThrough:function(d){ return d.readable; },
      pipeTo:function(){ return Promise.resolve(); } };
  }
  window.TextEncoderStream = TextEncoderStream;
  return 'streams-patched';
})()
"""

